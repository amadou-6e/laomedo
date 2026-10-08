"""The one-shot evidence writer must preserve failed attempts."""

import json
from pathlib import Path
import tempfile
import unittest

from experiments.exp100.probe_s2 import record_once


class ProbeS2RecordTests(unittest.TestCase):
    def test_failed_attempt_is_recorded_and_cannot_be_retried(self):
        with tempfile.TemporaryDirectory() as scratch:
            target = Path(scratch) / "observation-s2.json"

            def fail():
                raise AssertionError("synthetic fixture failed")

            observed = record_once(target, "a" * 40, run=fail)
            self.assertEqual(observed["status"], "failed")
            self.assertEqual(observed["error_type"], "AssertionError")
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), observed)
            with self.assertRaises(FileExistsError):
                record_once(target, "b" * 40, run=lambda: {"status": "passed"})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), observed)


if __name__ == "__main__":
    unittest.main()
