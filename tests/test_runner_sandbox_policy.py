"""Internal launch-policy regressions; real runtime evidence is separate."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from laomedo.agents.providers.codex.runner import CodexRunner as LocalRunner; from laomedo.agents.runtime.errors import RunnerError; from laomedo.agents.providers.codex.native.models import CodexLaunch
from laomedo.agents.providers.codex.preflight.models import DockerSelection


@unittest.skipUnless(__import__("importlib.util").util.find_spec("py_docker"), "Requires optional Docker runtime")
class RunnerSandboxPolicyTests(unittest.TestCase):
    def test_split_controller_token_is_not_a_control_environment(self):
        from laomedo.agents.providers.codex.split.server import SplitAppServer
        from laomedo.agents.providers.codex.settings import IMAGE_ID
        with tempfile.TemporaryDirectory() as temp, patch("py_docker.Client") as client, patch(
                "laomedo.agents.providers.codex.native.server.AppServer.__init__",side_effect=OSError("launch unavailable")) as launch:
            root=Path(temp); selected={"DOCKER_HOST":"unix:///selected.sock"}
            client.return_value.images.resolve.return_value=IMAGE_ID
            client.return_value.sessions.open.return_value.identity.id="a"*64
            client.return_value.sessions.open.return_value.read_frame.return_value=None
            with self.assertRaises(OSError):
                SplitAppServer(root,root,root,root,"profile",access_token="internal-test-token",docker_environment=selected)
            policy=launch.call_args.args[0]
            self.assertEqual(policy.to_container_spec().environment["ACCESS_TOKEN"].get_secret_value(),"internal-test-token")
            self.assertNotIn("ACCESS_TOKEN",client.call_args.kwargs["environment"])
            executor=client.return_value.sessions.open.call_args.args[0]
            self.assertNotIn("ACCESS_TOKEN",executor.spec.environment)
            client.return_value.sessions.open.return_value.close.assert_called_once()

    def test_split_permission_checks_use_selected_endpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); source=Path(__file__).resolve().parents[1] / "examples/github-pr"
            runner=LocalRunner(root / "state",root / "skills",source,split_executor=True,check_docker=False)
            server=MagicMock(); server.request.return_value={"result":{}}
            server.exec_probe.return_value.exit_code=1
            with patch.object(runner,"_open_server",return_value=server), patch(
                    "laomedo.agents.providers.codex.utils._advertised_models",return_value=[]):
                with self.assertRaisesRegex(RunnerError,"permission_preflight_failed"):
                    runner.preflight()
            self.assertEqual(server.exec_probe.call_count,4)
            for call in server.exec_probe.call_args_list:
                self.assertEqual(call.args[0][:2],["sh","-c"])

    def test_split_profile_failure_cleanup_keeps_endpoint(self):
        from docker.errors import NotFound
        from laomedo.agents.providers.codex.utils import _ensure_split_profile
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
            selection=DockerSelection(image_id="sha256:"+"a"*64,environment={"DOCKER_HOST":"unix:///selected.sock"})
            for split in (False,True):
                with patch("laomedo.agents.providers.codex.preflight.service.CodexPreflight.check",return_value=selection) as checked, patch(
                        "laomedo.agents.providers.codex.utils._ensure_split_profile") as profile, patch("py_docker.Client") as client:
                    runner=LocalRunner(root / str(split),root / "skills",source,split_executor=split)
                    checked.assert_called_once_with(runner.image,runner.image_id)
                    if split:
                        profile.assert_called_once_with(runner.profile,state=runner.state,env=selection.environment)
                    else:
                        client.assert_called_once_with(environment=selection.environment)
                        client.return_value.__enter__.return_value.volumes.exists.assert_called_once()

    def test_split_control_calls_keep_the_selected_endpoint(self):
        from laomedo.agents.providers.codex.split.server import SplitAppServer
        server=SplitAppServer.__new__(SplitAppServer); server._executor_client=MagicMock()
        server._executor_client.execution.run.return_value.exit_code=0
        server._executor_client.execution.run.return_value.stdout=b"verified"
        self.assertEqual(server._exec("owned",["codex","--version"]),"verified")
        self.assertEqual(server._executor_client.execution.run.call_args.args[:2],("owned",["codex","--version"]))

    def test_retired_cli_version_probe_cannot_return(self):
        """One implementation owns Codex startup image/version validation."""
        import inspect
        source = inspect.getsource(LocalRunner.__init__)
        self.assertNotIn('"--version"', source)
        self.assertNotIn('"{{.Id}}"', source)
        self.assertEqual(source.count("CodexPreflight(self.state).check("), 1)

    def test_changed_or_missing_packaged_profile_refuses_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            policy = root / "policy.json"
            policy.write_text('{"defaultAction":"SCMP_ACT_ALLOW"}')
            with patch("laomedo.agents.providers.codex.settings.SECCOMP", policy):
                with self.assertRaisesRegex(RunnerError, "seccomp_profile_changed"):
                    CodexLaunch(workspace=root,canonical=root,store_mount=root,image="sha256:"+"a"*64).to_container_spec()
                policy.unlink()
                with self.assertRaises(OSError):
                    CodexLaunch(workspace=root,canonical=root,store_mount=root,image="sha256:"+"a"*64).to_container_spec()

    def test_legacy_keeps_seccomp_and_split_controller_uses_default(self):
        from laomedo.agents.providers.codex.split.models import SplitLaunch
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
            selection = DockerSelection(image_id=approved, environment={"DOCKER_HOST": "unix:///local-test.sock"})
            with patch("laomedo.agents.providers.codex.preflight.service.CodexPreflight.check", return_value=selection) as checked, patch("py_docker.Client") as docker:
                runner = LocalRunner(root / "state", root / "skills", source,
                                     image_id=approved, transport=Capture)
                checked.assert_called_once_with(runner.image, approved)
                self.assertEqual(docker.call_args.kwargs["environment"], selection.environment)
            runner._open_server(root)
            self.assertEqual(approved, commands[0].image)
            self.assertNotEqual(runner.image, commands[0].image)
            with patch("laomedo.agents.providers.codex.preflight.service.CodexPreflight.check", side_effect=RunnerError("docker_image_digest_changed")):
                with self.assertRaisesRegex(RunnerError, "docker_image_digest_changed"):
                    LocalRunner(root / "mismatch", root / "skills", source,
                                image_id=approved)

    def test_wrong_cli_version_refuses_before_any_model_dispatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = Path(__file__).resolve().parents[1] / "examples/github-pr"
            approved = "sha256:" + "a" * 64
            with patch("laomedo.agents.providers.codex.preflight.service.CodexPreflight.check", side_effect=RunnerError("unsupported_codex_cli_version")), patch("subprocess.run") as docker:
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
        from laomedo.agents.providers.claude.container import ClaudeContainer
        from py_docker.errors import ConnectionConfigurationError
        with patch("py_docker.Client",side_effect=ConnectionConfigurationError("select local endpoint")):
            with self.assertRaisesRegex(RunnerError,"claude_container_configuration_invalid"):
                ClaudeContainer()
