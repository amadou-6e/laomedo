"""Internal controls only; live startup verification is recorded separately."""
import json
import socket
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import patch, Mock
from urllib.error import URLError
from urllib.request import Request, urlopen
from laomedo.runner_service import RunnerService, install_runner_service_routes, service_environment
from laomedo.local_runner import serve
try:
    from fastapi.testclient import TestClient
except ImportError:
    TestClient = None


class RunnerServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.config={'provider':'claude','state':str(self.root/'runner'),'skill_store':str(self.root/'registry'),
            'source':str(self.root/'source'),'executable':str(self.root/'claude.exe'),
            'port':18769,'max_model_turns':1}
        (self.root/'runner').mkdir();(self.root/'runner/api-token').write_text('internal-control')
        self.path=self.root/'config.json';self.path.write_text(json.dumps(self.config))
        self.service=RunnerService(self.path);self.url='http://127.0.0.1:18769'
        self.real_connect=socket.create_connection
        probe=patch('laomedo.runner_service.socket.create_connection', side_effect=ConnectionRefusedError())
        self.probe=probe.start(); self.addCleanup(probe.stop)

    def test_unconfigured_and_arbitrary_urls_cannot_start_any_process(self):
        with patch('laomedo.runner_service.subprocess.Popen') as spawn:
            self.assertEqual(RunnerService(None).start(self.url)['state'],'unmanaged')
            for url in ['https://external.test',self.url+'/path',self.url+'?port=5','http://127.0.0.1:12345']:
                self.assertFalse(self.service.start(url)['can_start'])
            spawn.assert_not_called()

    def test_service_start_excludes_host_secrets_and_provider_overrides(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY':'internal-only','OPENAI_API_KEY':'internal-only',
                'LANGFLOW_SECRET_KEY':'internal-only','DATABASE_URL':'internal-only',
                'CLAUDE_CONFIG_DIR':'unrelated','DOCKER_HOST':'docker-context','PATH':'runtime-path'}):
            for provider in ('claude','codex'):
                env=service_environment(provider)
                for key in ('ANTHROPIC_API_KEY','OPENAI_API_KEY','LANGFLOW_SECRET_KEY','DATABASE_URL','CLAUDE_CONFIG_DIR'):
                    self.assertNotIn(key,env)
                self.assertEqual(env['PATH'],'runtime-path')
                self.assertEqual('DOCKER_HOST' in env,provider=='codex')
            with patch.object(self.service.opener,'open',side_effect=URLError('offline')), \
                 patch('laomedo.runner_service.subprocess.Popen',return_value=Mock(poll=lambda:None)) as spawn:
                self.service.start(self.url)
            env=spawn.call_args.kwargs['env']
            for key in ('ANTHROPIC_API_KEY','OPENAI_API_KEY','LANGFLOW_SECRET_KEY','DATABASE_URL','CLAUDE_CONFIG_DIR'):
                self.assertNotIn(key,env)

    def test_concurrent_clicks_do_not_spawn_twice_or_change_turn_limit(self):
        (self.root/'runner/turn-ledger.json').write_text('{"attempted_turns":1}')
        with patch.object(self.service.opener,'open',side_effect=URLError('offline')), \
             patch('laomedo.runner_service.subprocess.Popen',return_value=Mock(poll=lambda:None)) as spawn:
            first=self.service.start(self.url);second=self.service.start(self.url)
        self.assertEqual(first['state'],'starting');self.assertEqual(second['state'],'starting')
        spawn.assert_called_once();args=spawn.call_args.args[0]
        self.assertEqual(args[args.index('--max-model-turns')+1],'1')
        self.assertEqual(args[1], '-c')
        self.assertEqual(args[3], str(Path(__file__).resolve().parents[1]))
        self.assertEqual(args[4], 'laomedo.claude_runner')
        self.assertEqual(json.loads((self.root/'runner/turn-ledger.json').read_text())['attempted_turns'],1)
        self.assertNotIn('shell',spawn.call_args.kwargs)

    def test_authenticated_health_reports_exhaustion_without_dispatch(self):
        self.probe.side_effect=self.real_connect
        ledger=self.root/'runner/turn-ledger.json';ledger.write_text('{"attempted_turns":1}')
        runner=SimpleNamespace(state=self.root/'runner',max_model_turns=1,provider='claude',api_token='internal-control')
        server=serve(runner,port=0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        self.config['port']=server.server_port;self.path.write_text(json.dumps(self.config))
        status=self.service.status('http://127.0.0.1:'+str(server.server_port))
        self.assertEqual(status,{'state':'ready','can_start':False,'remaining_turns':0})
        self.assertEqual(json.loads(ledger.read_text())['attempted_turns'],1)

    def test_wrong_provider_listener_never_launches_replacement(self):
        from io import BytesIO
        with patch.object(self.service.opener,'open',return_value=BytesIO(b'{"status":"ready","provider":"codex"}')), \
             patch('laomedo.runner_service.subprocess.Popen') as spawn:
            self.assertEqual(self.service.start(self.url)['state'],'unavailable');spawn.assert_not_called()

    def test_real_loopback_refusal_is_detected_on_this_platform(self):
        self.probe.side_effect = self.real_connect
        with socket.socket() as reserved:
            reserved.bind(('127.0.0.1', 0))
            self.config['port'] = reserved.getsockname()[1]
        self.path.write_text(json.dumps(self.config))
        with patch.object(self.service.opener, 'open', side_effect=URLError('offline')):
            self.assertEqual(self.service.status()['state'], 'offline')

    def test_health_timeout_with_existing_listener_never_starts_replacement(self):
        self.probe.side_effect = None
        self.probe.return_value = Mock(__enter__=Mock(), __exit__=Mock(return_value=False))
        with patch.object(self.service.opener, 'open', side_effect=TimeoutError()), \
             patch('laomedo.runner_service.subprocess.Popen') as spawn:
            result = self.service.start()
        self.assertEqual(result, {'state': 'unavailable', 'can_start': False,
                                 'reason': 'runner_identity_unverified'})
        spawn.assert_not_called()

    def test_startup_failure_is_retryable_and_does_not_return_logs_or_paths(self):
        self.service.process=Mock(poll=lambda:1)
        with patch.object(self.service.opener,'open',side_effect=URLError('offline')):
            result=self.service.status(self.url)
        self.assertEqual(result['reason'],'runner_start_failed');self.assertTrue(result['can_start'])
        self.assertNotIn(str(self.root),json.dumps(result))

    @unittest.skipIf(TestClient is None, 'optional FastAPI/httpx integration is not installed')
    def test_start_route_requires_authentication(self):
        from fastapi import FastAPI,Header,HTTPException
        app=FastAPI()
        def auth(authorization:str=Header(default='')):
            if authorization!='internal-auth':raise HTTPException(401)
            return object()
        install_runner_service_routes(app,auth,self.service)
        client=TestClient(app)
        with patch.object(self.service,'start',return_value={'state':'starting','can_start':False}) as start:
            self.assertEqual(client.post('/api/v1/laomedo/runner-service/start',params={'url':self.url}).status_code,401)
            start.assert_not_called()
            result=client.post('/api/v1/laomedo/runner-service/start',params={'url':self.url},headers={'Authorization':'internal-auth'})
            self.assertEqual(result.status_code,200);self.assertEqual(result.headers['cache-control'],'no-store')

    def test_default_host_service_needs_no_graph_url(self):
        with patch.object(self.service.opener, 'open', side_effect=URLError('offline')), \
             patch('laomedo.runner_service.subprocess.Popen') as spawn:
            spawn.return_value.poll.return_value = None
            self.assertEqual(self.service.status()['state'], 'offline')
            self.assertEqual(self.service.start()['state'], 'starting')
            command = spawn.call_args.args[0]
            self.assertEqual(command[command.index('--port') + 1], str(self.config['port']))
            self.assertEqual(command[command.index('--max-model-turns') + 1], '1')
            self.assertFalse(self.service.start('http://127.0.0.1:12345')['can_start'])
            self.assertEqual(spawn.call_count, 1)

if __name__=='__main__':unittest.main()
