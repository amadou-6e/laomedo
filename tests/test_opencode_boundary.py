"""Credential-free command recipe and MCP capability checks."""

from pathlib import Path
import hashlib
import json
import tempfile
import time
import unittest
import threading
import subprocess
from unittest.mock import Mock, patch
from urllib import error, request

from laomedo.opencode_boundary import (CommandBroker, IsolatedOpenCode, check_auth_fresh,
                                      worker_command, WORKER_IMAGE, WORKER_IMAGE_ID)
from laomedo.local_runner import RunnerError


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
            (profile / 'provider-options.json').write_text(json.dumps({'provider': {'opencode-go': {
                'options': {'headers': {}}}}}))
            broker = Mock()
            broker.server.server_port = 12345
            broker.token = 'synthetic-capability'
            def docker(args, **_kwargs):
                if args[:3] == ['docker', 'image', 'inspect']:
                    return Mock(stdout='fixture-image' if args[3] == 'fixture-controller' else WORKER_IMAGE_ID)
                return Mock(stdout='')
            with patch('laomedo.opencode_boundary.CommandBroker', return_value=broker), \
                 patch('laomedo.opencode_boundary.subprocess.run', side_effect=docker):
                with self.assertRaisesRegex(RunnerError, 'opencode_organization_context_invalid'):
                    IsolatedOpenCode(workspace, evidence, profile=profile,
                                     image='fixture-controller', image_id='fixture-image')
            broker.close.assert_called_once()

    def test_controller_mounts_auth_read_only_without_persistent_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile, workspace, evidence = self.fixture(Path(tmp), mode='provider_key')
            broker = Mock()
            broker.server.server_port = 12345
            broker.token = 'synthetic-capability'
            launch = []
            def docker(args, **_kwargs):
                if args[:3] == ['docker', 'image', 'inspect']:
                    return Mock(stdout='fixture-image' if args[3] == 'fixture-controller' else WORKER_IMAGE_ID)
                if args[:3] == ['docker', 'run', '-d']:
                    launch.extend(args)
                    raise subprocess.CalledProcessError(1, args)
                return Mock(stdout=b'', stderr=b'')
            with patch('laomedo.opencode_boundary.CommandBroker', return_value=broker), \
                 patch('laomedo.opencode_boundary.subprocess.run', side_effect=docker):
                with self.assertRaises(subprocess.CalledProcessError):
                    IsolatedOpenCode(workspace, evidence, profile=profile,
                                     image='fixture-controller', image_id='fixture-image')
            mounts = [launch[i + 1] for i, item in enumerate(launch) if item == '--mount']
            self.assertTrue(any('target=/home/runner/.local/share/opencode/auth.json,readonly' in x for x in mounts))
            self.assertFalse(any('target=/controller-auth.json' in x for x in mounts))
            self.assertNotIn('cp', launch)
            self.assertFalse((profile / 'sessions/auth.json').exists())
            broker.close.assert_called_once()

    def test_second_worker_request_rejected_while_one_is_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broker = CommandBroker(root, root, root, root)
            self.addCleanup(broker.close)
            entered, release = threading.Event(), threading.Event()
            def docker(args, **_kwargs):
                if args[:2] == ['docker', 'run']:
                    entered.set()
                    if not release.wait(3):
                        raise TimeoutError()
                return Mock(returncode=0, stdout='ok', stderr='')
            result = {}
            with patch('laomedo.opencode_boundary.subprocess.run', side_effect=docker):
                thread = threading.Thread(target=lambda: result.update(broker.execute('pwd')))
                thread.start()
                try:
                    self.assertTrue(entered.wait(3))
                    self.assertEqual(broker.execute('pwd')['stderr'], 'worker_busy')
                finally:
                    release.set()
                    thread.join(4)
            self.assertFalse(thread.is_alive())
            self.assertEqual(result['exit_code'], 0)

    def test_workers_stop_before_request_handlers_are_joined(self):
        broker = CommandBroker.__new__(CommandBroker)
        broker.lock = threading.Lock()
        broker.active = {'owned-worker'}
        calls = []
        broker.server = Mock()
        broker.server.shutdown.side_effect = lambda: calls.append('shutdown')
        broker.server.server_close.side_effect = lambda: calls.append('join-handlers')
        broker.thread = Mock()
        with patch('laomedo.opencode_boundary.subprocess.run', side_effect=lambda *_a, **_k: calls.append('stop-worker')):
            broker.close()
        self.assertEqual(calls, ['shutdown', 'stop-worker', 'join-handlers'])

    def test_worker_never_mounts_controller_profile_or_environment(self):
        args = worker_command("owned", Path("workspace"), Path("canonical"), Path("store"), "pwd")
        self.assertEqual(args[args.index("--network") + 1], "none")
        self.assertNotIn("-e", args)
        self.assertNotIn("--privileged", args)
        self.assertIn("ALL", args)
        mounts = [args[index + 1] for index, value in enumerate(args) if value == "--mount"]
        self.assertEqual(len(mounts), 3)
        self.assertTrue(any("target=/canonical,readonly" in value for value in mounts))
        self.assertTrue(any("target=/store,readonly" in value for value in mounts))
        self.assertFalse(any("auth" in value or "profile" in value for value in mounts))

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
