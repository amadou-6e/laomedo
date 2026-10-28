"""Credential-free command recipe and MCP capability checks."""

from pathlib import Path
import hashlib
import json
import tempfile
import time
import unittest
import threading
from unittest.mock import Mock, MagicMock; from unittest.mock import patch
from urllib import error; from urllib import request

from laomedo.agents.providers.opencode.boundary import CommandBroker; from laomedo.agents.providers.opencode.boundary import IsolatedOpenCode; from laomedo.agents.providers.opencode.utils import check_auth_fresh; from laomedo.agents.providers.codex.settings import IMAGE_ID
from laomedo.agents.runtime.errors import RunnerError
from py_docker.errors import DockerOperationError, CleanupUnconfirmedError
from py_docker.execution.models import CommandResult
CONTROLLER_ID = 'sha256:'+'a'*64
ENDPOINT = 'npipe:////./pipe/dockerDesktopLinuxEngine'



class BoundaryTests(unittest.TestCase):
    @staticmethod
    def fixture(root, *, mode='console_token', expiry=None):
        profile = root / 'profile'
        profile.mkdir()
        key = 'synthetic-provider-credential'
        (profile / 'auth.json').write_text(json.dumps({'opencode-go': {'type': 'api', 'key': key}}))
        (profile / 'auth-validity.json').write_text(json.dumps({
            'credential_mode': mode, 'expires_at_ms': expiry,
            'credential_sha256': hashlib.sha256(key.encode()).hexdigest()}))
        workspace = root / 'workspace'
        skill = workspace / '.agents/skills/sample'
        skill.mkdir(parents=True)
        (skill / 'SKILL.md').write_text('fixture')
        evidence = root / 'evidence'
        evidence.mkdir()
        return profile, workspace, evidence

    def test_console_token_expiry_and_key_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile, _, _ = self.fixture(root, expiry=int(time.time() * 1000) + 60000)
            with self.assertRaisesRegex(RunnerError, 'opencode_console_token_refresh_required'):
                check_auth_fresh(profile)
            (profile / 'auth-validity.json').write_text(json.dumps({
                'credential_mode': 'console_token', 'expires_at_ms': int(time.time() * 1000) + 600000,
                'credential_sha256': hashlib.sha256(b'synthetic-provider-credential').hexdigest()}))
            check_auth_fresh(profile)
            (profile / 'auth.json').write_text(json.dumps({'opencode-go': {'type': 'api', 'key': 'changed-key'}}))
            with self.assertRaisesRegex(RunnerError, 'opencode_auth_validity_mismatch'):
                check_auth_fresh(profile)

    def test_failed_controller_options_close_broker(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile, workspace, evidence = self.fixture(Path(tmp), mode='provider_key')
            profile.joinpath('provider-options.json').write_text(json.dumps({'provider':{'opencode-go':{'options':{'headers':{}}}}}))
            with patch('py_docker.Client') as client, patch('laomedo.agents.providers.opencode.boundary.CommandBroker') as broker:
                client.return_value.__enter__.return_value.connection.endpoint = ENDPOINT
                with self.assertRaisesRegex(RunnerError,'opencode_organization_context_invalid'):
                    IsolatedOpenCode(workspace,evidence,profile=profile,image='controller',image_id=CONTROLLER_ID)
                broker.return_value.close.assert_called_once()
                client.return_value.sessions.open.assert_not_called()


    def test_controller_mounts_auth_read_only_without_persistent_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile,workspace,evidence=self.fixture(Path(tmp),mode='provider_key')
            with patch('py_docker.Client') as client, patch('laomedo.agents.providers.opencode.boundary.CommandBroker') as broker:
                client.return_value.__enter__.return_value.connection.endpoint=ENDPOINT
                broker.return_value.error_code=None
                broker.return_value.token='internal-capability'
                broker.return_value.server.server_port=12345
                client.return_value.sessions.open.side_effect=DockerOperationError('internal refusal')
                with self.assertRaisesRegex(RunnerError,'opencode_controller_startup_failed'):
                    IsolatedOpenCode(workspace,evidence,profile=profile,image='controller',image_id=CONTROLLER_ID)
                spec=client.return_value.sessions.open.call_args.args[0].spec
                self.assertEqual(spec.image,CONTROLLER_ID)
                self.assertEqual(spec.ports,{'4096/tcp':None})
                mounts={m.target:m for m in spec.mounts}
                self.assertTrue(mounts['/home/runner/.local/share/opencode/auth.json'].read_only)
                self.assertTrue(mounts['/draft'].read_only)
                self.assertFalse(mounts['/home/runner/.local/share/opencode'].read_only)
                self.assertNotIn('/controller-auth.json',mounts)
                self.assertFalse(profile.joinpath('sessions/auth.json').exists())
                self.assertNotIn('OPENCODE_SERVER_PASSWORD',spec.model_dump_json())
                broker.return_value.close.assert_called_once()


    def test_trusted_agent_hook_extends_defaults_before_read_only_config_mount(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile,workspace,evidence=self.fixture(Path(tmp),mode='provider_key')
            def configure(config):
                self.assertEqual(config['permission']['skill'],{'*':'deny','sample':'allow'})
                self.assertTrue(config['tools']['skill'])
                config['tools']['task']=True
            with patch('py_docker.Client') as client, patch('laomedo.agents.providers.opencode.boundary.CommandBroker') as broker:
                client.return_value.__enter__.return_value.connection.endpoint=ENDPOINT
                broker.return_value.error_code=None
                broker.return_value.token='internal-capability'
                broker.return_value.server.server_port=12345
                client.return_value.sessions.open.side_effect=DockerOperationError('internal refusal')
                with self.assertRaises(RunnerError):
                    IsolatedOpenCode(workspace,evidence,profile=profile,image='controller',image_id=CONTROLLER_ID,configure_agents=configure)
                config=json.loads(next(evidence.glob('controller-*/config.json')).read_text())
                self.assertTrue(config['tools']['task'])
                spec=client.return_value.sessions.open.call_args.args[0].spec
                self.assertTrue(next(m for m in spec.mounts if m.target=='/controller-config.json').read_only)


    def test_second_worker_request_rejected_while_one_is_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            broker=CommandBroker(root,root,root,root,docker_endpoint=ENDPOINT)
            self.addCleanup(broker.close)
            entered,release=threading.Event(),threading.Event()
            def run(job):
                entered.set()
                self.assertTrue(release.wait(3))
                return CommandResult(exit_code=0,stdout=b'ok',stderr=b'')
            result={}
            with patch('py_docker.Client') as client:
                client.return_value.__enter__.return_value.jobs.run.side_effect=run
                thread=threading.Thread(target=lambda:result.update(broker.execute('pwd')))
                thread.start()
                try:
                    self.assertTrue(entered.wait(3))
                    self.assertEqual(broker.execute('pwd')['stderr'],'worker_busy')
                finally:
                    release.set();thread.join(4)
            self.assertFalse(thread.is_alive())
            self.assertEqual(result['exit_code'],0)


    def test_workers_stop_before_request_handlers_are_joined(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);broker=CommandBroker(root,root,root,root,docker_endpoint=ENDPOINT)
            broker.capacity.acquire()
            closed=threading.Event()
            thread=threading.Thread(target=lambda:(broker.close(),closed.set()))
            thread.start()
            try:
                time.sleep(0.6)
                self.assertFalse(closed.is_set())
                self.assertTrue(broker.closed)
            finally:
                broker.capacity.release();thread.join(4)
            self.assertTrue(closed.is_set())
            with self.assertRaisesRegex(RunnerError,'opencode_command_service_closed'):
                broker.execute('pwd')


    def test_credential_binding_is_keyed_stable_and_changes_with_credentials(self):
        from laomedo.agents.providers.opencode.utils import _credential_binding
        with tempfile.TemporaryDirectory() as tmp:
            profile,_,_=self.fixture(Path(tmp),mode='provider_key')
            validity_path=profile/'auth-validity.json'
            validity=json.loads(validity_path.read_text())
            first=_credential_binding(profile)
            self.assertNotEqual(first,validity['credential_sha256'])
            self.assertEqual(first,_credential_binding(profile))
            validity['credential_sha256']=hashlib.sha256(b'rotated-test-key').hexdigest()
            validity_path.write_text(json.dumps(validity))
            self.assertNotEqual(first,_credential_binding(profile))

    def test_cleanup_transport_failure_is_not_claimed_as_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);broker=CommandBroker(root,root,root,root,docker_endpoint=ENDPOINT)
            with patch('py_docker.Client') as client:
                client.return_value.__enter__.return_value.jobs.run.side_effect=CleanupUnconfirmedError('internal cleanup')
                with self.assertRaisesRegex(RunnerError,'opencode_container_cleanup_unverified'):
                    broker.execute('pwd')
            with self.assertRaisesRegex(RunnerError,'opencode_container_cleanup_unverified'):
                broker.close()


    def test_worker_never_mounts_controller_profile_or_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);broker=CommandBroker(root,root,root,root,docker_endpoint=ENDPOINT,worker_image_id=CONTROLLER_ID)
            self.addCleanup(broker.close)
            with patch('py_docker.Client') as client:
                client.return_value.__enter__.return_value.jobs.run.return_value=CommandResult(exit_code=0,stdout=b'ok',stderr=b'')
                broker.execute('pwd')
                job=client.return_value.__enter__.return_value.jobs.run.call_args.args[0]
            spec=job.spec
            self.assertEqual(spec.image,CONTROLLER_ID)
            self.assertEqual(spec.network_mode,'none')
            self.assertEqual(spec.environment,{})
            self.assertEqual(spec.cap_drop,['ALL'])
            self.assertEqual(len(spec.mounts),3)
            self.assertTrue(next(m for m in spec.mounts if m.target=='/canonical').read_only)
            self.assertTrue(next(m for m in spec.mounts if m.target=='/store').read_only)
            self.assertTrue(job.receipt_path.is_relative_to(root))


    def test_mcp_requires_bearer_capability_and_rejects_unknown_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            broker = CommandBroker(path, path, path, path)
            self.addCleanup(broker.close)
            url = "http://127.0.0.1:" + str(broker.server.server_port) + "/mcp"
            payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode()
            with self.assertRaises(error.HTTPError) as failure:
                request.urlopen(request.Request(url, data=payload))
            self.assertEqual(failure.exception.code, 403)
            headers = {"Authorization": "Bearer " + broker.token, "Content-Type": "application/json"}
            with request.urlopen(request.Request(url, data=payload, headers=headers)) as response:
                body = json.load(response)
            self.assertEqual(body["result"]["tools"][0]["name"], "exec")
            with self.assertRaisesRegex(ValueError, "unknown_worker_tool"):
                broker.rpc("tools/call", {"name": "read_personal_profile"})


if __name__ == "__main__":
    unittest.main()
