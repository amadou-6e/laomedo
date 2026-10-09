"""No-Docker guards for the distinct S4-02 diagnostic identity."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from experiments.exp100 import probe_s4_diag


class ProbeS4DiagnosticTests(unittest.TestCase):
    def test_failed_diagnostic_consumes_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "observation-s4-02.json"
            with patch.object(probe_s4_diag, "run", return_value={
                    "identity": probe_s4_diag.IDENTITY, "status": "unknown"}):
                result = probe_s4_diag.record_once(target, "a" * 40)
                self.assertEqual(result["status"], "unknown")
                self.assertEqual(json.loads(target.read_text())["status"], "unknown")
                with self.assertRaises(FileExistsError):
                    probe_s4_diag.record_once(target, "a" * 40)

    def test_exception_is_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "observation-s4-02.json"
            with patch.object(probe_s4_diag, "run",
                              side_effect=RuntimeError("private temp path")):
                probe_s4_diag.record_once(target, "b" * 40)
            payload = target.read_text()
            self.assertNotIn("private temp path", payload)
            self.assertEqual(json.loads(payload)["error_class"], "RuntimeError")

    def test_diagnostic_script_has_bounded_stage_vocabulary(self):
        script = probe_s4_diag.SCRIPT.read_text(encoding="utf-8")
        for stage in ("mount_access", "git_init", "baseline_fetch",
                      "bundle_unbundle", "fsck", "commit_type"):
            self.assertIn(f"stage={stage}", script)
        self.assertIn("S4_FAILED_STAGE=$stage", script)
        self.assertIn("test -r /trusted/.git/HEAD", script)
        self.assertNotIn("curl ", script)

    def test_mount_checks_against_generated_worktree_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            trusted, bundle, _, _ = probe_s4_diag.probe_s4._fixture(
                Path(directory))
            self.assertTrue((trusted / ".git" / "HEAD").is_file())
            shell = shutil.which("sh")
            if shell is None and shutil.which("git"):
                git_root = Path(shutil.which("git")).resolve().parents[1]
                candidate = git_root / "bin" / "sh.exe"
                if candidate.is_file():
                    shell = str(candidate)
            if shell is None:
                self.skipTest("POSIX shell unavailable")
            check = subprocess.run(
                [shell, "-c", 'test -r "$1/.git/HEAD" && test -r "$2"',
                 "sh", str(trusted), str(bundle)], capture_output=True,
                text=True, timeout=10, check=False)
            self.assertEqual(check.returncode, 0, check.stderr)


if __name__ == "__main__":
    unittest.main()
