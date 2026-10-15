"""Internal launch-policy regressions; real runtime evidence is separate."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from laomedo.local_runner import LocalRunner, RunnerError, _docker_prefix


class RunnerSandboxPolicyTests(unittest.TestCase):
    def test_changed_or_missing_packaged_profile_refuses_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            policy = root / "policy.json"
            policy.write_text('{"defaultAction":"SCMP_ACT_ALLOW"}')
            with patch("laomedo.local_runner.SECCOMP", policy):
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
            with patch("laomedo.local_runner.subprocess.run", return_value=
                       subprocess.CompletedProcess([], 0, approved, "")):
                runner = LocalRunner(root / "state", root / "skills", source,
                                     image_id=approved, transport=Capture)
            runner._open_server(root)
            self.assertIn(approved, commands[0])
            self.assertNotIn(runner.image, commands[0])
            with patch("laomedo.local_runner.subprocess.run", return_value=
                       subprocess.CompletedProcess([], 0, "sha256:" + "b" * 64, "")):
                with self.assertRaisesRegex(RunnerError, "docker_image_digest_changed"):
                    LocalRunner(root / "mismatch", root / "skills", source,
                                image_id=approved)

    def test_local_image_override_rejects_tags_and_git_mode(self):
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
