"""No-Docker guards for the distinct S4-02 diagnostic identity."""

import json
from pathlib import Path
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
        self.assertNotIn("curl ", script)


if __name__ == "__main__":
    unittest.main()
