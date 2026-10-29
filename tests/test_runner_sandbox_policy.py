"""Internal launch-policy regressions; real runtime evidence is separate."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from laomedo.agents.agents.codex.agent import CodexAgent as LocalRunner; from laomedo.agents.errors import RunnerError; from laomedo.agents.agents.codex.controller.models import CodexLaunch


@unittest.skipUnless(__import__("importlib.util").util.find_spec("py_docker"), "Requires optional Docker runtime")
class RunnerSandboxPolicyTests(unittest.TestCase):
    def test_split_controller_token_is_not_a_control_environment(self):
        from laomedo.agents.agents.codex.split.models import SplitLaunch
        from laomedo.agents.agents.codex.controller.models import SplitPolicy
        from laomedo.agents.agents.codex.controller.service import CodexController
        from unittest.mock import Mock
        root = Path("/test")
        executor = Mock()
        executor.session.identity.id = "a" * 64
        launch = CodexLaunch(workspace=root, canonical=root, store_mount=root, image="sha256:" + "b" * 64)
        with tempfile.TemporaryDirectory() as temp, patch("py_docker.Client") as client, patch("laomedo.agents.agents.codex.split.executor.Executor", return_value=executor):
            controller = CodexController(launch, Path(temp), env={"DOCKER_HOST": "unix:///selected.sock"}, split=SplitPolicy(access_token="private-test-token"))
            spec = client.return_value.sessions.open.call_args.args[0].spec
            self.assertEqual(spec.environment["ACCESS_TOKEN"].get_secret_value(), "private-test-token")
            self.assertNotIn("ACCESS_TOKEN", client.call_args.kwargs["environment"])
            self.assertNotIn("private-test-token", spec.environment["LAOMEDO_CODEX_ARGS"].get_secret_value())
            controller._close_resources()
            executor.close.assert_called_once_with()

    def test_split_permission_checks_use_selected_endpoint(self):
        from unittest.mock import AsyncMock
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runner = LocalRunner(root / "state", root / "skills", Path(__file__).resolve().parents[1] / "examples/github-pr", split_executor=True, check_docker=False)
            server = MagicMock(initialize=AsyncMock(), models=AsyncMock(return_value=[]), preflight=AsyncMock(return_value=1), close=AsyncMock())
            with patch.object(runner, "_open_server", return_value=server):
                with self.assertRaisesRegex(RunnerError, "permission_preflight_failed"):
                    runner.preflight()
            self.assertEqual(server.preflight.await_count, 4)

    def test_split_profile_failure_cleanup_keeps_endpoint(self):
        from docker.errors import NotFound
        from laomedo.agents.agents.codex.utils import _ensure_split_profile
        with tempfile.TemporaryDirectory() as temp, patch("py_docker.Client") as client:
            selected={"DOCKER_HOST":"unix:///selected.sock"}; docker=client.return_value.__enter__.return_value
            docker.volumes.exists.return_value=False
            docker.images.resolve.return_value="sha256:"+"a"*64
            docker.jobs.run.return_value.exit_code=1
            with self.assertRaisesRegex(RunnerError,"docker_control_failed"):
                _ensure_split_profile("profile",state=Path(temp),env=selected)
            client.assert_called_once_with(environment=selected)
            docker.sdk.volumes.remove.assert_not_called()
            self.assertEqual(docker.jobs.run.call_args.args[0].receipt_path,Path(temp)/"profile-init.json")

    def test_both_modes_use_one_preflight_before_profile_access(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); source=Path(__file__).resolve().parents[1] / "examples/github-pr"
            selection={"DOCKER_HOST":"unix:///selected.sock"}
            for split in (False,True):
                with patch("laomedo.agents.agents.codex.agent.CodexRunner._check_container",return_value=selection) as checked, patch(
                        "laomedo.agents.agents.codex.utils._ensure_split_profile") as profile, patch("py_docker.Client") as client:
                    runner=LocalRunner(root / str(split),root / "skills",source,split_executor=split)
                    checked.assert_called_once_with()
                    if split:
                        profile.assert_called_once_with(runner.profile,state=runner.state,env=selection)
                    else:
                        client.assert_called_once_with(environment=selection)
                        client.return_value.__enter__.return_value.volumes.exists.assert_called_once()

    def test_split_control_calls_keep_the_selected_endpoint(self):
        from laomedo.agents.agents.codex.split.executor import Executor
        server=Executor.__new__(Executor); server.client=MagicMock()
        server.client.execution.run.return_value.exit_code=0
        server.client.execution.run.return_value.stdout=b"verified"
        self.assertEqual(server._exec("owned",["codex","--version"]),"verified")
        self.assertEqual(server.client.execution.run.call_args.args[:2],("owned",["codex","--version"]))

    def test_retired_cli_version_probe_cannot_return(self):
        """One implementation owns Codex startup image/version validation."""
        import inspect
        source = inspect.getsource(LocalRunner.__init__)
        self.assertNotIn('"--version"', source)
        self.assertNotIn('"{{.Id}}"', source)
        self.assertEqual(source.count("self._check_container()"), 1)

    def test_changed_or_missing_packaged_profile_refuses_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            policy = root / "policy.json"
            policy.write_text('{"defaultAction":"SCMP_ACT_ALLOW"}')
            with patch("laomedo.agents.agents.codex.settings.SECCOMP", policy):
                with self.assertRaisesRegex(RunnerError, "seccomp_profile_changed"):
                    CodexLaunch(workspace=root,canonical=root,store_mount=root,image="sha256:"+"a"*64).to_container_spec()
                policy.unlink()
                with self.assertRaises(OSError):
                    CodexLaunch(workspace=root,canonical=root,store_mount=root,image="sha256:"+"a"*64).to_container_spec()

    def test_legacy_keeps_seccomp_and_split_controller_uses_default(self):
        from laomedo.agents.agents.codex.split.models import SplitLaunch
        root=Path("/test")
        normal=CodexLaunch(workspace=root,canonical=root,store_mount=root,image="sha256:"+"a"*64).to_container_spec()
        self.assertEqual(normal.cap_drop,["ALL"])
        self.assertIn("no-new-privileges",normal.security_opt)
        self.assertTrue(any(value.startswith("seccomp=") for value in normal.security_opt))
        split=SplitLaunch(workspace=root,canonical=root,store_mount=root,image="sha256:"+"a"*64,executor_id="b"*64).to_container_spec()
        self.assertEqual(split.security_opt,["no-new-privileges"])
        self.assertEqual(split.network_mode,"container:"+"b"*64)

    def test_local_image_requires_exact_match_and_launches_by_digest(self):
        approved = "sha256:" + "a" * 64
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = Path(__file__).resolve().parents[1] / "examples/github-pr"
            commands = []
            class Capture:
                def __init__(self, command, evidence):
                    commands.append(command)
            selection = {"DOCKER_HOST": "unix:///local-test.sock"}
            with patch("laomedo.agents.agents.codex.agent.CodexRunner._check_container", return_value=selection) as checked, patch("py_docker.Client") as docker:
                runner = LocalRunner(root / "state", root / "skills", source,
                                     image_id=approved, transport=Capture)
                checked.assert_called_once_with()
                self.assertEqual(docker.call_args.kwargs["environment"], selection)
            runner._open_server(root)
            self.assertEqual(approved, commands[0].image)
            self.assertNotEqual(runner.image, commands[0].image)
            with patch("laomedo.agents.agents.codex.agent.CodexRunner._check_container", side_effect=RunnerError("docker_image_digest_changed")):
                with self.assertRaisesRegex(RunnerError, "docker_image_digest_changed"):
                    LocalRunner(root / "mismatch", root / "skills", source,
                                image_id=approved)

    def test_wrong_cli_version_refuses_before_any_model_dispatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = Path(__file__).resolve().parents[1] / "examples/github-pr"
            approved = "sha256:" + "a" * 64
            with patch("laomedo.agents.agents.codex.agent.CodexRunner._check_container", side_effect=RunnerError("unsupported_codex_cli_version")), patch("subprocess.run") as docker:
                with self.assertRaisesRegex(RunnerError, "unsupported_codex_cli_version"):
                    LocalRunner(root / "state", root / "skills", source, image_id=approved)
            docker.assert_not_called()
            self.assertFalse((root / "state/turn-ledger.json").exists())

    def test_local_image_override_rejects_tags_git_and_split_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = Path(__file__).resolve().parents[1] / "examples/github-pr"
            for image_id in ("latest", "sha256:bad", "sha256:" + "A" * 64):
                with self.subTest(image_id=image_id), self.assertRaisesRegex(
                        RunnerError, "invalid_local_image_id"):
                    LocalRunner(root / "state", root / "skills", source, image_id=image_id)
            with self.assertRaisesRegex(RunnerError, "invalid_local_image_id"):
                LocalRunner(root / "state", root / "skills", source,
                            image_id="sha256:" + "a" * 64, git_workspace=True)
            with self.assertRaisesRegex(RunnerError, "invalid_local_image_id"):
                LocalRunner(root / "state", root / "skills", source,
                            image_id="sha256:" + "a" * 64, split_executor=True)


    def test_claude_endpoint_configuration_maps_to_descriptive_code(self):
        from laomedo.agents.agents.claude.container import ClaudeContainer
        from py_docker.errors import ConnectionConfigurationError
        with patch.object(ClaudeContainer,"check_supervisor"), patch("py_docker.Client",side_effect=ConnectionConfigurationError("select local endpoint")):
            with self.assertRaisesRegex(RunnerError,"claude_container_configuration_invalid"):
                ClaudeContainer()
