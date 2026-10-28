"""Internal launch-policy regressions; real runtime evidence is separate."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from laomedo.agents.providers.codex.runner import CodexRunner as LocalRunner; from laomedo.agents.runtime.errors import RunnerError; from laomedo.agents.providers.codex.utils import _docker_prefix
from laomedo.agents.providers.codex.preflight.models import DockerSelection


class RunnerSandboxPolicyTests(unittest.TestCase):
    def test_both_modes_use_one_preflight_before_profile_access(self):
        """The SDK check replaces the CLI version probe in both execution modes."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = Path(__file__).resolve().parents[1] / "examples/github-pr"
            selection = DockerSelection(image_id="sha256:" + "a" * 64,
                                        environment={"DOCKER_HOST": "unix:///selected.sock"})
            for split in (False, True):
                with self.subTest(split=split), patch(
                    "laomedo.agents.providers.codex.preflight.service.CodexPreflight.check",
                    return_value=selection,
                ) as checked, patch(
                    "laomedo.agents.providers.codex.utils._ensure_split_profile"
                ) as profile, patch("subprocess.run") as command:
                    runner = LocalRunner(root / str(split), root / "skills", source,
                                         split_executor=split)
                    checked.assert_called_once_with(runner.image, runner.image_id)
                    if split:
                        command.assert_not_called()
                        profile.assert_called_once_with(runner.profile, env=selection.environment)
                        with patch("laomedo.agents.providers.codex.servers.SplitAppServer") as server:
                            runner._open_server(root)
                            self.assertEqual(server.call_args.kwargs["docker_environment"], selection.environment)
                    else:
                        profile.assert_not_called()
                        self.assertEqual(command.call_args.args[0][:3], ["docker", "volume", "inspect"])
                        self.assertEqual(command.call_args.kwargs["env"], selection.environment)

    def test_split_control_calls_keep_the_selected_endpoint(self):
        """Subsequent split operations use the same endpoint as preflight."""
        from laomedo.agents.providers.codex.servers import SplitAppServer
        server = SplitAppServer.__new__(SplitAppServer)
        server.docker_environment = {"DOCKER_HOST": "unix:///selected.sock"}
        with patch("laomedo.agents.providers.codex.utils._docker_checked") as checked:
            server._docker_checked("inspect", "owned", timeout=9)
            checked.assert_called_once_with("inspect", "owned", timeout=9,
                                            env=server.docker_environment)

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
                    _docker_prefix(root, root, root)
                policy.unlink()
                with self.assertRaises(OSError):
                    _docker_prefix(root, root, root)

    def test_legacy_keeps_seccomp_and_split_controller_uses_default(self):
        root = Path("/test")
        command = _docker_prefix(root, root, root)
        self.assertIn("no-new-privileges", command)
        self.assertEqual(command[command.index("--cap-drop") + 1], "ALL")
        self.assertTrue(any(arg.startswith("seccomp=") for arg in command))
        self.assertNotIn("seccomp=unconfined", command)
        self.assertNotIn("--privileged", command)
        split = _docker_prefix(root, root, root, nested_sandbox=False)
        self.assertFalse(any(arg.startswith("seccomp=") for arg in split))

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
            with patch("laomedo.agents.providers.codex.preflight.service.CodexPreflight.check", return_value=selection) as checked, patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, "", "")) as docker:
                runner = LocalRunner(root / "state", root / "skills", source,
                                     image_id=approved, transport=Capture)
                checked.assert_called_once_with(runner.image, approved)
                self.assertEqual(docker.call_args.kwargs["env"], selection.environment)
            runner._open_server(root)
            self.assertIn(approved, commands[0])
            self.assertNotIn(runner.image, commands[0])
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
