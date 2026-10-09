"""Credential-free checks for the extended shared turn ledger."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

try:
    from experiments.exp22 import phase_e_ui
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    phase_e_ui = None


@unittest.skipUnless(phase_e_ui is not None, "experiment source is not installed in the wheel")
class PhaseELedgerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "turns.json"
        self.path.write_text(json.dumps({"cap": 12, "attempts": [
            {"id": str(index), "result": "prior"} for index in range(4)]}),
            encoding="utf-8")
        patcher = mock.patch.object(phase_e_ui, "LEDGER", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_reservation_preserves_four_prior_turns_and_counts_timeout(self):
        attempt, used = phase_e_ui._reserve(self.path.parent)
        self.assertEqual(used, 5)
        rows = json.loads(self.path.read_text(encoding="utf-8"))["attempts"]
        self.assertEqual([row["id"] for row in rows[:4]], ["0", "1", "2", "3"])
        self.assertEqual(rows[-1]["result"], "submitted_unknown")
        phase_e_ui._reserve(self.path.parent, attempt_id=attempt, result="timeout_unknown")
        rows = json.loads(self.path.read_text(encoding="utf-8"))["attempts"]
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[-1]["result"], "timeout_unknown")

    def test_cap_and_lock_refuse_a_new_submission(self):
        ledger = json.loads(self.path.read_text(encoding="utf-8"))
        ledger["attempts"].extend({"id": str(index)} for index in range(4, 12))
        self.path.write_text(json.dumps(ledger), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "extended_ledger_exhausted"):
            phase_e_ui._reserve(self.path.parent)
        self.assertEqual(len(json.loads(self.path.read_text())["attempts"]), 12)
        self.path.with_suffix(".lock").write_text("held", encoding="ascii")
        with self.assertRaises(FileExistsError):
            phase_e_ui._reserve(self.path.parent)


if __name__ == "__main__":
    unittest.main()
