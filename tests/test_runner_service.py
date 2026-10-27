"""Internal controls only; live startup verification is recorded separately."""
import json
import laomedo
import socket
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import patch, Mock
from urllib.error import URLError
from urllib.request import Request, urlopen
from laomedo.host.runner_service import RunnerService, install_runner_service_routes, service_environment
from laomedo.agents.local_runner import LocalRunner, serve
try:
    from fastapi.testclient import TestClient
except ImportError:
    TestClient = None


class RunnerServiceTests(unittest.TestCase):
    def test_normal_defaults_ignore_historical_exhaustion_without_dispatch(self):
        """The managed command's ordinary defaults must not install a zero-turn gate."""
        state = self.root / 'normal-state'
        source = self.root / 'normal-repo' / 'source'
        source.mkdir(parents=True)
        (source.parent / '.git').mkdir()
        runner = LocalRunner(state, self.root / 'normal-store', source,
                             check_docker=False, supervise_containers=False)
        history = state / 'turn-ledger.json'
        historical_bytes = b'{"attempted_turns":99,"max_authorized_turns":1}'
        history.write_bytes(historical_bytes)
        runner._turn_available()
        self.assertEqual(runner._reserve_turn(), 1)
        self.assertEqual(history.read_bytes(), historical_bytes)
        restarted = LocalRunner(state, self.root / 'normal-store', source,
                                check_docker=False, supervise_containers=False)
        restarted._turn_available()
        self.assertEqual(restarted._reserve_turn(), 2)
        # Even malformed historical evidence is not a future-run authorization gate.
        history.write_bytes(b'historical evidence, not runtime configuration')
        restarted._turn_available()
        self.assertEqual(restarted._reserve_turn(), 3)
        self.assertEqual(history.read_bytes(), b'historical evidence, not runtime configuration')
        self.assertEqual(json.loads((state / 'attempt-count.json').read_text())['attempted_turns'], 3)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.config={'provider':'claude','state':str(self.root/'runner'),'skill_store':str(self.root/'registry'),
            'source':str(self.root/'source'),'executable':str(self.root/'claude.exe'),
            'port':18769}
        (self.root/'runner').mkdir();(self.root/'runner/api-token').write_text('internal-control')
        self.path=self.root/'config.json';self.path.write_text(json.dumps(self.config))
        self.service=RunnerService(self.path);self.url='http://127.0.0.1:18769'
        # Internal controls; these are not evidence of the host's Docker state.
        docker = patch('laomedo.host.runner_service.check_docker', return_value=None)
        self.docker = docker.start(); self.addCleanup(docker.stop)
        self.real_connect=socket.create_connection
        probe=patch('laomedo.host.runner_service.socket.create_connection', side_effect=ConnectionRefusedError())
        self.probe=probe.start(); self.addCleanup(probe.stop)

    def test_unconfigured_and_arbitrary_urls_cannot_start_any_process(self):
        with patch('laomedo.host.runner_service.subprocess.Popen') as spawn:
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
                self.assertEqual('DOCKER_HOST' in env,provider in {'codex','claude'})
            with patch.object(self.service.opener,'open',side_effect=URLError('offline')), \
                 patch('laomedo.host.runner_service.subprocess.Popen',return_value=Mock(poll=lambda:None)) as spawn:
                self.service.start(self.url)
            env=spawn.call_args.kwargs['env']
            for key in ('ANTHROPIC_API_KEY','OPENAI_API_KEY','LANGFLOW_SECRET_KEY','DATABASE_URL','CLAUDE_CONFIG_DIR'):
                self.assertNotIn(key,env)

    def test_turn_login_mirror_is_opt_in_and_uses_only_trusted_destination(self):
        self.probe.side_effect = self.real_connect
        from urllib.request import Request, urlopen
        import os
        events = []
        def dispatch(body, response_gate):
            events.append('dispatch')
            return {'status':'running', 'run_id':'aeb54b12-3ca7-43a7-97b3-762dadc94721'}
        runner = SimpleNamespace(state=self.root/'runner', provider='claude', api_token='internal-control',
            container=SimpleNamespace(profile='laomedo-claude-profile', image_id='sha256:'+'a'*64),
            start_async=dispatch)
        server=serve(runner,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        for enabled in ('','1'):
            events.clear()
            with patch.dict(os.environ, {'LAOMEDO_CLAUDE_MIRROR_HOST_LOGIN':enabled}), \
                 patch('laomedo.host.credentials.claude_login.mirror_login',side_effect=lambda *args:events.append('mirror')) as mirror:
                req=Request('http://127.0.0.1:'+str(server.server_port)+'/v1/runs/async',
                    data=json.dumps({'profile':'untrusted','image':'untrusted'}).encode(),
                    headers={'Authorization':'Bearer internal-control','Content-Type':'application/json'})
                with urlopen(req,timeout=5) as reply:self.assertEqual(reply.status,202)
            self.assertEqual(events, ['dispatch'])
            mirror.assert_not_called()

    def test_explicit_login_mirror_is_deferred_to_task_not_startup(self):
        self.config['mirror_host_claude_login'] = True
        self.path.write_text(json.dumps(self.config))
        with patch.object(self.service.opener, 'open', side_effect=URLError('offline')), \
             patch('laomedo.host.credentials.claude_login.mirror_login') as mirror, \
             patch('laomedo.host.runner_service.subprocess.Popen', return_value=Mock(poll=lambda:None)) as spawn:
            result = self.service.start(self.url)
        mirror.assert_not_called()
        self.assertEqual(result['state'], 'starting')
        self.assertEqual(spawn.call_args.kwargs['env']['LAOMEDO_CLAUDE_MIRROR_HOST_LOGIN'], '1')

    def test_slow_mirror_waits_for_ack_and_precedes_execution(self):
        gate=threading.Event();entered=threading.Event();release=threading.Event();executed=threading.Event()
        def slow_copy():
            entered.set();release.wait(5)
        runner=SimpleNamespace(_mirror_host_login=slow_copy, _execute=lambda *a,**kw:executed.set())
        worker=threading.Thread(target=LocalRunner._async_worker,args=(runner,'run','task',gate))
        worker.start()
        try:
            self.assertFalse(entered.wait(.1))
            gate.set();self.assertTrue(entered.wait(2))
            self.assertFalse(executed.is_set())
        finally:
            release.set();gate.set();worker.join(5)
        self.assertTrue(executed.is_set())

    def test_async_copy_failure_is_recorded_without_model_dispatch(self):
        from laomedo.agents.local_runner import RunnerError
        record={'status':'prepared'}
        def fail(): raise RunnerError('claude_host_login_expired')
        runner=SimpleNamespace(_mirror_host_login=fail, _execute=Mock(), control_lock=threading.Lock(),
            status=lambda run_id:record, _run_dir=lambda run_id:self.root)
        gate=threading.Event();gate.set()
        LocalRunner._async_worker(runner,'run','task',gate)
        runner._execute.assert_not_called()
        result=json.loads((self.root/'record.json').read_text())
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['error_category'],'claude_host_login_expired')

    def test_concurrent_clicks_do_not_spawn_twice_or_restore_legacy_turn_limit(self):
        self.config['max_model_turns']=1
        self.path.write_text(json.dumps(self.config))
        (self.root/'runner/turn-ledger.json').write_text('{"attempted_turns":1}')
        with patch.object(self.service.opener,'open',side_effect=URLError('offline')), \
             patch('laomedo.host.runner_service.subprocess.Popen',return_value=Mock(poll=lambda:None)) as spawn:
            first=self.service.start(self.url);second=self.service.start(self.url)
        self.assertEqual(first['state'],'starting');self.assertEqual(second['state'],'starting')
        spawn.assert_called_once();args=spawn.call_args.args[0]
        self.assertNotIn('--max-model-turns',args)
        self.assertNotIn('max_model_turns',self.service.config(self.url))
        self.assertEqual(args[1], '-c')
        self.assertEqual(args[3], str(Path(laomedo.__file__).resolve().parent.parent))
        self.assertEqual(args[4], 'laomedo.agents.providers.claude_runner')
        self.assertEqual(spawn.call_args.kwargs['cwd'], Path(laomedo.__file__).resolve().parent.parent)
        self.assertEqual(json.loads((self.root/'runner/turn-ledger.json').read_text())['attempted_turns'],1)
        self.assertNotIn('shell',spawn.call_args.kwargs)

    def test_authenticated_health_ignores_legacy_exhaustion_without_dispatch(self):
        self.probe.side_effect=self.real_connect
        ledger=self.root/'runner/turn-ledger.json';ledger.write_text('{"attempted_turns":1}')
        runner=SimpleNamespace(state=self.root/'runner',max_model_turns=1,provider='claude',api_token='internal-control')
        server=serve(runner,port=0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        self.config['port']=server.server_port;self.path.write_text(json.dumps(self.config))
        status=self.service.status('http://127.0.0.1:'+str(server.server_port))
        self.assertEqual(status,{'state':'ready','can_start':False})
        ledger.write_text('malformed historical verification ledger')
        self.assertEqual(self.service.status('http://127.0.0.1:'+str(server.server_port)),status)
        self.assertEqual(ledger.read_text(),'malformed historical verification ledger')

    def test_wrong_provider_listener_never_launches_replacement(self):
        from io import BytesIO
        with patch.object(self.service.opener,'open',return_value=BytesIO(b'{"status":"ready","provider":"codex"}')), \
             patch('laomedo.host.runner_service.subprocess.Popen') as spawn:
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
             patch('laomedo.host.runner_service.subprocess.Popen') as spawn:
            result = self.service.start()
        self.assertEqual(result, {'state': 'unavailable', 'can_start': False,
                                 'reason': 'runner_identity_unverified'})
        spawn.assert_not_called()

    def test_previously_ready_api_exit_is_not_reported_as_startup_failure(self):
        from io import BytesIO
        process = Mock()
        process.poll.return_value = None
        self.service.process = process
        with patch.object(self.service.opener, 'open', return_value=BytesIO(b'{"status":"ready","provider":"claude","remaining_turns":0}')):
            self.assertEqual(self.service.status()['state'], 'ready')
        process.poll.return_value = 1
        with patch.object(self.service.opener, 'open', side_effect=URLError('offline')):
            self.assertEqual(self.service.status(), {'state':'offline', 'can_start':True, 'reason':'runner_local_offline'})
        self.service.process = Mock(poll=lambda: 1)
        with patch.object(self.service.opener, 'open', side_effect=URLError('offline')):
            self.assertEqual(self.service.status()['reason'], 'runner_start_failed')

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

    def test_cancelled_startup_never_binds_a_listener(self):
        from laomedo.host.startup_control import startup_gate
        gate = self.root / 'serve.lock'
        with startup_gate(gate) as marker: marker.with_suffix('.cancel').touch()
        with patch.dict('os.environ', {'LAOMEDO_STARTUP_GATE':str(gate)}), patch('laomedo.agents.local_runner.ThreadingHTTPServer') as bind:
            with self.assertRaises(SystemExit): serve(SimpleNamespace(),port=0)
        bind.assert_not_called()
        self.assertTrue(gate.with_suffix(".cancelled").exists())

    def test_listener_publication_blocks_later_cancellation(self):
        gate = self.root / 'serve.lock'
        with patch.dict('os.environ', {'LAOMEDO_STARTUP_GATE':str(gate)}):
            server = serve(SimpleNamespace(),port=0)
        server.server_close()
        self.assertTrue(gate.with_suffix('.listening').exists())

    def test_cancel_only_matching_owned_startup(self):
        child = Mock(); child.poll.return_value = None
        self.service.process = child; self.service.startup_id = 'attempt-one'
        self.service.startup_gate_path = self.root / 'startup.lock'
        with patch.object(self.service, 'status', return_value={'state':'starting','can_start':False}):
            self.service.cancel_start('old-attempt')
            self.assertFalse(self.service.startup_gate_path.with_suffix('.cancel').exists())
            result = self.service.cancel_start('attempt-one')
        child.terminate.assert_not_called()
        self.assertEqual(result['state'], 'cancelling')
        self.assertTrue(self.service.startup_gate_path.with_suffix('.cancel').exists())
        child.poll.return_value = 0
        self.assertNotEqual(self.service._offline_state()["reason"], "runner_start_cancelled")
        self.service.startup_gate_path.with_suffix(".cancelled").touch()
        self.assertEqual(self.service._offline_state()['reason'], 'runner_start_cancelled')

    def test_cancel_never_stops_ready_or_uncertain_listener(self):
        for state in ('ready', 'unavailable'):
            child = Mock(); self.service.process = child; self.service.startup_id = 'attempt-one'; self.service.startup_gate_path = self.root / 'startup.lock'
            with patch.object(self.service, 'status', return_value={'state':state,'can_start':False}):
                self.assertEqual(self.service.cancel_start('attempt-one')['state'], state)
            child.terminate.assert_not_called()

    def test_cancel_refuses_startup_that_bound_listener_after_status_probe(self):
        child = Mock(); self.service.process = child; self.service.startup_id = 'attempt-one'
        self.service.startup_gate_path = self.root / 'startup.lock'
        self.service.startup_gate_path.with_suffix('.listening').touch()
        with patch.object(self.service, 'status', return_value={'state':'starting','can_start':False}):
            self.service.cancel_start('attempt-one')
        child.terminate.assert_not_called()

    @unittest.skipIf(TestClient is None, 'optional FastAPI/httpx integration is not installed')
    def test_cancel_route_requires_auth_and_exact_startup_identity(self):
        from fastapi import FastAPI, Header, HTTPException
        app = FastAPI()
        def auth(authorization: str = Header(default='')):
            if authorization != 'internal-auth': raise HTTPException(401)
        install_runner_service_routes(app, auth, self.service)
        client = TestClient(app)
        with patch.object(self.service, 'cancel_start', return_value={'state':'offline','can_start':True}) as cancel:
            self.assertEqual(client.post('/api/v1/laomedo/runner-service/cancel-start', params={'startup_id':'attempt-one'}).status_code,401)
            cancel.assert_not_called()
            result = client.post('/api/v1/laomedo/runner-service/cancel-start', params={'startup_id':'attempt-one'}, headers={'Authorization':'internal-auth'})
            self.assertEqual(result.status_code,200); cancel.assert_called_once_with('attempt-one')
            self.assertEqual(result.headers['cache-control'],'no-store')

    def test_default_host_service_needs_no_graph_url(self):
        with patch.object(self.service.opener, 'open', side_effect=URLError('offline')), \
             patch('laomedo.host.runner_service.subprocess.Popen') as spawn:
            spawn.return_value.poll.return_value = None
            self.assertEqual(self.service.status()['state'], 'offline')
            self.assertEqual(self.service.start()['state'], 'starting')
            command = spawn.call_args.args[0]
            self.assertEqual(command[command.index('--port') + 1], str(self.config['port']))
            self.assertNotIn('--max-model-turns', command)
            self.assertFalse(self.service.start('http://127.0.0.1:12345')['can_start'])
            self.assertEqual(spawn.call_count, 1)

    def test_docker_prerequisites_block_start_without_disclosing_cli_output(self):
        for reason in ('runner_docker_not_installed', 'runner_docker_unavailable', 'runner_docker_check_unconfirmed'):
            self.docker.return_value = reason
            with patch.object(self.service.opener, 'open', side_effect=URLError('offline')), \
                 patch('laomedo.host.runner_service.subprocess.Popen') as spawn:
                value = self.service.start()
                self.assertEqual(value, {'state':'prerequisite', 'can_start':False, 'reason':reason, 'runner_state':'offline'})
                spawn.assert_not_called()

    def test_start_rechecks_docker_even_after_cached_healthy_poll(self):
        with patch.object(self.service.opener, 'open', side_effect=URLError('offline')), \
             patch('laomedo.host.runner_service.subprocess.Popen') as spawn:
            self.assertTrue(self.service.status()['can_start'])
            self.docker.return_value = 'runner_docker_unavailable'
            self.assertFalse(self.service.start()['can_start'])
            self.assertEqual(self.docker.call_count, 2)
            spawn.assert_not_called()

    def test_slow_overlapping_check_does_not_authorize_spawn(self):
        self.service.docker_lock.acquire()
        try:
            with patch.object(self.service.opener, 'open', side_effect=URLError('offline')), \
                 patch('laomedo.host.runner_service.subprocess.Popen') as spawn:
                self.assertEqual(self.service.start()['reason'], 'runner_docker_check_unconfirmed')
                spawn.assert_not_called()
        finally:
            self.service.docker_lock.release()

    def test_running_api_does_not_imply_docker_is_ready(self):
        from io import BytesIO
        self.docker.return_value = 'runner_docker_unavailable'
        with patch.object(self.service.opener, 'open', return_value=BytesIO(b'{"provider":"claude","status":"ready"}')):
            self.assertEqual(self.service.status()['state'], 'prerequisite')

    def test_confirmed_cancellation_is_retained_when_docker_is_down(self):
        self.docker.return_value = 'runner_docker_unavailable'
        state = self.service._with_docker({'state':'offline','can_start':True,'reason':'runner_start_cancelled'})
        self.assertTrue(state['startup_cancelled'])
        self.assertFalse(state['can_start'])

if __name__=='__main__':unittest.main()
