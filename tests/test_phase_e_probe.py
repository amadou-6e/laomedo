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

    def test_disconnect_cannot_count_as_visible_stop(self):
        observed = {"stop_click_begin_epoch": 10.0,
                    "context_close_begin_epoch": 13.0,
                    "runner_terminal_signal_seen": True}
        self.assertTrue(phase_e_ui._ui_attribution(
            observed, [{"at_epoch_seconds": 11.0}], 12.0))
        for cancel, terminal, close in [(9.0, 12.0, 13.0),
                                        (14.0, 15.0, 13.0),
                                        (11.0, 14.0, 13.0)]:
            observed["context_close_begin_epoch"] = close
            self.assertFalse(phase_e_ui._ui_attribution(
                observed, [{"at_epoch_seconds": cancel}], terminal))
        observed["runner_terminal_signal_seen"] = False
        self.assertFalse(phase_e_ui._ui_attribution(
            observed, [{"at_epoch_seconds": 11.0}], 12.0))

    def test_embedded_component_mismatch_refuses_before_reservation(self):
        root = self.path.parent
        flow_path = root / "examples/native-codex-node/flow.json"
        flow_path.parent.mkdir(parents=True)
        component_dir = root / "components/laomedo"
        component_dir.mkdir(parents=True)
        nodes = []
        for kind, filename in (("LaomedoCodexAgent", "codex_agent.py"),
                               ("LaomedoSkill", "skill.py")):
            (component_dir / filename).write_text("pinned code", encoding="utf-8")
            nodes.append({"data": {"type": kind, "node": {"template": {
                "code": {"value": "pinned code"}}}}})
        flow_path.write_text(json.dumps({"data": {"nodes": nodes}}), encoding="utf-8")
        with mock.patch.object(phase_e_ui, "ROOT", root):
            self.assertEqual(len(phase_e_ui._flow_code_pins()), 2)
            nodes[0]["data"]["node"]["template"]["code"]["value"] = "stale code"
            flow_path.write_text(json.dumps({"data": {"nodes": nodes}}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "flow_component_code_mismatch"):
                phase_e_ui._flow_code_pins()


if __name__ == "__main__":
    unittest.main()
