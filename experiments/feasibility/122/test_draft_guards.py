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
                restore(root / "missing", draft, before)
            self.assertEqual(tree_hash(inventory(draft)), before)
            frozen = root / "snapshot"
            snapshot(draft, frozen)
            (draft / "SKILL.md").write_text("drift", encoding="utf-8")
            self.assertEqual(restore(frozen, draft, before), before)

    def test_issue_turn_ledger_counts_failed_attempts(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            self.assertEqual(reserve_turn(state, limit=2), 1)
            self.assertEqual(reserve_turn(state, limit=2), 2)
            with self.assertRaisesRegex(ValueError, "issue_122_turn_cap_reached"):
                reserve_turn(state, limit=2)

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
