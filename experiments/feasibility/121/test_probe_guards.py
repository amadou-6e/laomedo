"""Focused, credential-free checks for the #121 runner boundaries."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shared import (BudgetLedger, fingerprint, prepare_state_dir,
                     redact_message, restore_workspace_snapshot,
                     snapshot_workspace)


class ProbeGuardTests(unittest.TestCase):
    def test_state_inside_git_is_rejected_before_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".git").mkdir()
            state = root / "private-state"
            self.assertEqual(prepare_state_dir(state)["refused"],
                             "state_dir_inside_git_tree")
            self.assertFalse(state.exists())

    def test_snapshot_restore_and_missing_snapshot_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            project = state / "project"
            project.mkdir()
            (project / "notes.txt").write_text("before", encoding="utf-8")
            snapshot = state / "snapshots" / "run1"
            snapshot.parent.mkdir()
            expected = snapshot_workspace(state, project, snapshot)
            (project / "drift.txt").write_text("drift", encoding="utf-8")
            drifted = fingerprint(project)
            with self.assertRaises(FileNotFoundError):
                restore_workspace_snapshot(
                    state, project, state / "snapshots" / "missing", expected)
            self.assertEqual(fingerprint(project), drifted)
            self.assertEqual(restore_workspace_snapshot(
                state, project, snapshot, expected), expected)
            self.assertFalse((project / "drift.txt").exists())

    def test_budget_is_shared_and_persistent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "settings"
            first = BudgetLedger(root, state, cap="1", max_calls=2)
            reservation = first.reserve(0.6)
            first.settle(reservation, 0.8, "success")
            second = BudgetLedger(root, root / "stream", cap="1", max_calls=2)
            with self.assertRaisesRegex(ValueError, "spend cap"):
                second.reserve(0.3)
            second.reserve(0.2)
            with self.assertRaisesRegex(ValueError, "model-call cap"):
                first.reserve(0.01)

    def test_sanitizer_keeps_only_synthetic_skill_names(self):
        class SystemMessage:
            subtype = "init"
            data = {"skills": ["fixture-121-project", "private-skill-name"],
                    "session_id": "synthetic-id", "model": "synthetic-model"}

        class ToolUseBlock:
            id = "synthetic-tool-id"
            name = "Skill"
            input = {"skill": "private-skill-name", "safe": "fixture-121-project"}

        class AssistantMessage:
            model = "synthetic-model"
            session_id = "synthetic-id"
            stop_reason = None
            content = [ToolUseBlock()]
            usage = {}

        class ResultMessage:
            subtype = "error_during_execution"
            is_error = True
            num_turns = 1
            session_id = "synthetic-id"
            total_cost_usd = None
            api_error_status = 500
            terminal_reason = "test"
            errors = ["private error text"]
            usage = {}
            model_usage = {}

        views = [redact_message(message) for message in
                 (SystemMessage(), AssistantMessage(), ResultMessage())]
        self.assertEqual(views[0]["skill_names"], ["fixture-121-project"])
        self.assertEqual(views[0]["unrecognized_skill_count"], 1)
        self.assertEqual(views[1]["blocks"][0]["skill_args"],
                         {"safe": "fixture-121-project"})
        self.assertNotIn("private-skill-name", str(views))
        self.assertNotIn("private error text", str(views))


if __name__ == "__main__":
    unittest.main()
