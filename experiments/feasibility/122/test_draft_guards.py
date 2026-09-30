import tempfile
import subprocess
import os
import unittest
from pathlib import Path

from probe_draft_guards import (
    BASE_SKILL, evaluate_edit, inventory, restore, run_cases, snapshot,
    tree_hash,
)
from probe_codex_edit import reserve_turn


class DraftGuardTests(unittest.TestCase):
    def test_allowed_edit_is_reviewable_without_changing_base(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = evaluate_edit(
                "allowed", lambda draft: (draft / "SKILL.md").write_text(
                    BASE_SKILL + "Example: amber.\n", encoding="utf-8"),
                Path(temporary))
        self.assertTrue(report["promotion_eligible"])
        self.assertTrue(report["canonical_unchanged"])
        self.assertIn("+Example: amber.", report["patch"])
        self.assertIsNone(report["agent_run_id"])

    def test_forbidden_and_partial_edits_are_ineligible(self):
        cases = run_cases()["cases"]
        for name in ("forbidden_path", "partial_failure", "timeout",
                     "concurrent_base_change", "escaping_symlink"):
            self.assertFalse(cases[name].get("promotion_eligible", False), name)
        self.assertIn("forbidden_path",
                      cases["forbidden_path"]["validation"]["errors"])
        self.assertIn("base_revision_conflict",
                      cases["concurrent_base_change"]["validation"]["errors"])

    def test_missing_snapshot_fails_before_modification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            draft = root / "draft"
            draft.mkdir()
            (draft / "SKILL.md").write_text(BASE_SKILL, encoding="utf-8")
            before = tree_hash(inventory(draft))
            with self.assertRaises(ValueError):
                restore(root / "missing", draft, before, root)
            self.assertEqual(tree_hash(inventory(draft)), before)
            frozen = root / "snapshot"
            snapshot(draft, frozen)
            (draft / "SKILL.md").write_text("drift", encoding="utf-8")
            narrow_root = root / "narrow"
            narrow_root.mkdir()
            with self.assertRaisesRegex(ValueError, "restore_path_outside_run_root"):
                restore(frozen, draft, before, narrow_root)
            self.assertEqual((draft / "SKILL.md").read_text(encoding="utf-8"),
                             "drift")
            self.assertEqual(restore(frozen, draft, before, root), before)

    def test_issue_turn_ledger_counts_failed_attempts(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            self.assertEqual(reserve_turn(state, limit=2), 1)
            self.assertEqual(reserve_turn(state, limit=2), 2)
            with self.assertRaisesRegex(ValueError, "issue_122_turn_cap_reached"):
                reserve_turn(state, limit=2)

    def test_supplemental_turn_uses_existing_ledger(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            (state / "turn-budget-122.json").write_text(
                '{"attempted_turns": 6}\n', encoding="utf-8")
            self.assertEqual(reserve_turn(state), 7)
            with self.assertRaisesRegex(ValueError, "issue_122_turn_cap_reached"):
                reserve_turn(state)

    def test_agent_denial_requires_exact_target_and_failed_command(self):
        from probe_agent_forbidden_write import denied_command_items
        target = Path(r"C:\fixture\forbidden\agent-marker.txt")
        denied = {"method": "item/completed", "params": {"item": {
            "type": "commandExecution", "status": "failed", "exitCode": 1,
            "command": r"Set-Content C:\\fixture\\forbidden\\agent-marker.txt",
            "aggregatedOutput": "Access is denied"}}}
        unrelated = {"method": "item/completed", "params": {"item": {
            "type": "commandExecution", "status": "failed", "exitCode": 1,
            "command": r"Set-Content C:\fixture\other.txt",
            "aggregatedOutput": "Access is denied"}}}
        self.assertEqual(len(denied_command_items([denied, unrelated], target)), 1)
        self.assertEqual(denied_command_items([unrelated], target), [])

    def test_symlink_in_inventory_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside"
            outside.mkdir()
            draft = root / "draft"
            draft.mkdir()
            try:
                (draft / "link").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable on this host")
            with self.assertRaisesRegex(ValueError, "link_or_junction_in_tree"):
                inventory(draft)

    @unittest.skipUnless(os.name == "nt", "Windows junction test")
    def test_windows_junction_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside"
            outside.mkdir()
            draft = root / "draft"
            draft.mkdir()
            link = draft / "examples"
            result = subprocess.run(["cmd", "/c", "mklink", "/J",
                                     str(link), str(outside)],
                                    capture_output=True, text=True)
            if result.returncode != 0:
                self.skipTest("junction creation unavailable on this host")
            with self.assertRaisesRegex(ValueError, "link_or_junction_in_tree"):
                inventory(draft)


if __name__ == "__main__":
    unittest.main()
