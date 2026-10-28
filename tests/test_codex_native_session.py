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
                                image="sha256:"+"a"*64,run_id="run",launch_token="private",
                                capability=root.joinpath("private/grant.secret"),mediator_url="http://127.0.0.1",mediator_instance="internal")
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
            session.read_line.side_effect=[
                Frame(channel="stdout",data='{"method":"notice","params":{"text":"caf\u00e9"}}\n'.encode()),
                Frame(channel="stderr",data=b'private-token\n'),None]
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

    def test_reader_start_failure_cleans_the_open_session(self):
        """A local thread-start failure cannot strand a created controller."""
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            launch=CodexLaunch(workspace=root,canonical=root,store_mount=root,image="sha256:"+"a"*64)
            with patch("py_docker.Client") as client, patch("threading.Thread.start",side_effect=RuntimeError("internal thread control")):
                with self.assertRaisesRegex(RunnerError,"runner_transport_failed"):
                    AppServer(launch,root)
                client.return_value.sessions.open.return_value.close.assert_called_once_with()
                client.return_value.close.assert_called_once_with()

    def test_late_reader_completion_releases_deferred_resources_once(self):
        """A reported slow-reader failure does not leak resources after it exits."""
        import threading
        entered,release=threading.Event(),threading.Event()
        def late_read():
            entered.set()
            release.wait(timeout=2)
            return None
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            launch=CodexLaunch(workspace=root,canonical=root,store_mount=root,image="sha256:"+"a"*64)
            with patch("py_docker.Client") as client:
                client.return_value.sessions.open.return_value.read_line.side_effect=late_read
                server=AppServer(launch,root)
                self.assertTrue(entered.wait(timeout=1))
                with patch.object(server.reader,"join"):
                    with self.assertRaisesRegex(RunnerError,"runner_transport_failed"):
                        server.close()
                self.assertFalse(server.log.closed)
                release.set()
                server.reader.join(timeout=2)
                self.assertFalse(server.reader.is_alive())
                self.assertTrue(server.log.closed)
                client.return_value.close.assert_called_once_with()


class RetirementAndCatalogueTests(unittest.TestCase):
    """Keep retired imports out and catalogue coverage on the new producer."""

    def test_old_normal_cli_server_is_retired(self):
        root=Path(__file__).resolve().parents[1]
        package=root.joinpath("src/laomedo/agents/providers/codex")
        self.assertFalse(package.joinpath("servers.py").exists())
        self.assertFalse(package.joinpath("split/transport.py").exists())
        self.assertNotIn("def _docker_prefix",package.joinpath("utils.py").read_text())
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
        codes=set()
        producers=[root.joinpath("src/laomedo/agents/providers/codex/native",module) for module in ("server.py","models.py","base.py","settings.py")]
        producers += [root.joinpath("src/laomedo/agents/providers/codex/split",module) for module in ("server.py","models.py")]
        for module in producers:
            tree=ast.parse(module.read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.Call) and getattr(node.func,"id",getattr(node.func,"attr",""))=="RunnerError" and node.args:
                    codes.update(value.value.split(":",1)[0] for value in ast.walk(node.args[0]) if isinstance(value,ast.Constant) and isinstance(value.value,str))
        self.assertTrue(codes)
        self.assertEqual(codes-set(catalogue),set())
        self.assertNotIn("operator",catalogue["container_termination_unverified"]["recovery"])

    def test_recovered_metadata_is_removed_but_run_history_is_preserved(self):
        """Only successfully reconciled metadata folders are disposable."""
        from laomedo.agents.providers.codex.preflight.service import CodexPreflight
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for folder in ("runs","catalog","preflight"):
                directory=root.joinpath(folder,"identity")
                directory.mkdir(parents=True)
                directory.joinpath(settings.NATIVE_RECEIPT_FILENAME).write_text("internal control")
                directory.joinpath("history.json").write_text("retained execution evidence")
            client=Mock()
            client.sessions.recover.side_effect=lambda pending:pending.unlink()
            CodexPreflight(root)._recover_sessions(client)
            self.assertTrue(root.joinpath("runs/identity/history.json").exists())
            self.assertTrue(root.joinpath("catalog/identity/history.json").exists())
            self.assertTrue(root.joinpath("preflight/identity/history.json").exists())


    def test_host_budgets_validate_before_launch_attempt_marker(self):
        """An invalid host setting must not be recorded as dispatch."""
        root=Path(__file__).resolve().parents[1]
        source=root.joinpath("src/laomedo/agents/providers/codex/runner.py").read_text()
        self.assertLess(source.index("transport_settings = _native_settings.Settings.load()"), source.index("launch_attempted = True"))


    @unittest.skipUnless(find_spec("py_docker"),"Requires optional Docker runtime")
    def test_executor_receipt_is_recovered_and_unresolved_intent_is_retained(self):
        from laomedo.agents.providers.codex.preflight.service import CodexPreflight
        from laomedo.agents.providers.codex.runner import CodexRunner
        from py_docker.errors import CleanupUnconfirmedError
        with tempfile.TemporaryDirectory() as temp:
            state=Path(temp); root=state.joinpath("catalog","metadata"); root.mkdir(parents=True)
            runner=CodexRunner.__new__(CodexRunner); runner.state=state
            controller=runner._receipt_path(root)
            executor=controller.with_name(controller.stem+"-executor.json")
            executor.write_text("internal control")
            self.assertTrue(runner._pending_receipts(root))
            client=Mock(); client.sessions.recover.side_effect=CleanupUnconfirmedError("internal cleanup")
            with self.assertRaises(CleanupUnconfirmedError):
                CodexPreflight(state)._recover_sessions(client)
            self.assertTrue(executor.exists()); self.assertTrue(root.exists())
            client.sessions.recover.side_effect=lambda pending:pending.unlink()
            CodexPreflight(state)._recover_sessions(client)
            self.assertFalse(runner._pending_receipts(root))
            client.sessions.recover.assert_called_with(executor)
