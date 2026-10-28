"""Internal SDK-boundary controls; no model or live integration acceptance."""

import ast
import hashlib
import json
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import Mock, patch

from laomedo.agents.providers.codex import settings
from laomedo.agents.providers.codex.native.models import CodexLaunch
from laomedo.agents.providers.codex.native.server import AppServer
from laomedo.agents.runtime.errors import RunnerError


@unittest.skipUnless(find_spec("py_docker"), "Requires the optional Docker runtime")
class NativeSessionTests(unittest.TestCase):
    """Guard delegation, policy, byte framing and failure cleanup without Docker."""

    def test_launch_preserves_sandbox_mounts_and_lease_binding(self):
        """The direct SDK spec carries the same reviewed application restrictions."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            launch = CodexLaunch(workspace=root,canonical=root,store_mount=root,
                                image="sha256:"+"a"*64,run_id="run",launch_token="private")
            spec = launch.to_container_spec()
            self.assertEqual((spec.user,spec.network_mode,spec.working_dir),("10001:10001","bridge","/draft"))
            self.assertFalse(spec.read_only)
            self.assertTrue(spec.stdin_open)
            self.assertEqual(spec.cap_drop,["ALL"])
            self.assertEqual((spec.pids_limit,spec.mem_limit),(128,"1g"))
            policy = next(value[len("seccomp="):] for value in spec.security_opt if value.startswith("seccomp="))
            self.assertEqual(hashlib.sha256(policy.encode()).hexdigest(),settings.SECCOMP_SHA256)
            mounts = {mount.target:mount for mount in spec.mounts}
            self.assertEqual(mounts["/home/runner/.codex"].type,"volume")
            self.assertEqual(mounts["/home/runner/.codex"].source,settings.VOLUME)
            self.assertTrue(mounts["/canonical"].read_only)
            self.assertFalse(mounts["/store"].read_only)
            self.assertEqual(spec.labels["laomedo.run_id"].get_secret_value(),"run")
            self.assertNotIn("private",launch.model_dump_json())

    def test_native_reader_buffers_utf8_and_redacts_across_frames(self):
        """Use the actual constructor and line reader over an injected SDK boundary."""
        from py_docker.containers.models import ContainerState
        from py_docker.streams.models import Frame

        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            launch=CodexLaunch(workspace=root,canonical=root,store_mount=root,image="sha256:"+"a"*64)
            session=Mock()
            session.read_frame.side_effect=[
                Frame(channel="stdout",data=b'{"method":"notice","params":{"text":"caf\xc3'),
                Frame(channel="stderr",data=b'private-'),
                Frame(channel="stdout",data=b'\xa9"}}\n'),
                Frame(channel="stderr",data=b'token\n'),None]
            session.state.return_value=ContainerState(running=False,exit_code=0,removed=False)
            with patch("py_docker.Client") as client, patch("subprocess.Popen") as cli:
                client.return_value.sessions.open.return_value=session
                server=AppServer(launch,root,lifetime_seconds=321,secret_redactions=("private-token",))
                server.reader.join(timeout=2)
                self.assertTrue(server.streams_closed)
                self.assertEqual(server.messages.get_nowait()["params"]["text"],"café")
                request=client.return_value.sessions.open.call_args.args[0]
                self.assertEqual(request.limits.seconds,321)
                self.assertEqual(request.spec.command[-2:],["app-server","--stdio"])
                self.assertTrue(server._transport_exited())
                server.close()
                cli.assert_not_called()
                session.close.assert_called_once_with()
            self.assertEqual(root.joinpath("stderr.log").read_text(),"[REDACTED_RUN_CAPABILITY]\n")

    def test_failed_open_retains_safe_public_code_without_cli_fallback(self):
        """Unconfirmed SDK creation maps safely and never launches a second path."""
        from py_docker.errors import CleanupUnconfirmedError
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            launch=CodexLaunch(workspace=root,canonical=root,store_mount=root,image="sha256:"+"a"*64)
            with patch("py_docker.Client") as client, patch("subprocess.Popen") as cli:
                client.return_value.sessions.open.side_effect=CleanupUnconfirmedError("internal launch control")
                with self.assertRaisesRegex(RunnerError,"container_termination_unverified"):
                    AppServer(launch,root)
                cli.assert_not_called()
                client.return_value.close.assert_called_once_with()


class RetirementAndCatalogueTests(unittest.TestCase):
    """Keep retired imports out and catalogue coverage on the new producer."""

    def test_old_normal_cli_server_is_retired(self):
        root=Path(__file__).resolve().parents[1]
        package=root.joinpath("src/laomedo/agents/providers/codex")
        self.assertFalse(package.joinpath("servers.py").exists())
        source=package.joinpath("native/server.py").read_text()
        tree=ast.parse(source)
        imports={alias.name for node in ast.walk(tree) if isinstance(node,ast.Import) for alias in node.names}
        self.assertNotIn("subprocess",imports)
        self.assertFalse(any(isinstance(node,ast.Name) and node.id=="_docker_prefix" for node in ast.walk(tree)))
        for path in root.joinpath("src/laomedo").rglob("*.py"):
            self.assertNotIn("providers.codex.servers",path.read_text(),str(path))

    def test_new_native_transport_failures_are_catalogued(self):
        root=Path(__file__).resolve().parents[1]
        catalogue=json.loads(root.joinpath("frontend/langflow-skill-viewer/node-error-catalog.json").read_text())
        tree=ast.parse(root.joinpath("src/laomedo/agents/providers/codex/native/server.py").read_text())
        codes=set()
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=="RunnerError" and node.args:
                codes.update(value.value for value in ast.walk(node.args[0]) if isinstance(value,ast.Constant) and isinstance(value.value,str))
        self.assertTrue(codes)
        self.assertEqual(codes-set(catalogue),set())
