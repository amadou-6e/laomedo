import json
from pathlib import Path
import tempfile
import unittest

from laomedo.skill_store import (ConflictError, SkillStore, SkillStoreError,
                                 inventory, tree_hash)


BASE = ("---\nname: fixture-core\ndescription: Synthetic skill.\n---\n\n"
        "Rule: answer amber.\n")
POLICY = {
    "policy_id": "fixture-core-policy", "revision_id": "1",
    "allowed_paths": ["SKILL.md", "examples/amber.md"],
    "allowed_suffixes": [".md"], "allow_new_files": True,
    "allow_scripts": False, "allow_dependencies": False, "allow_assets": False,
    "required_frontmatter": ["name", "description"],
    "permitted_validation_commands": ["structural-v1"],
    "max_files": 2, "max_file_bytes": 8192,
}


class SkillStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.source = root / "source"
        self.source.mkdir()
        (self.source / "SKILL.md").write_text(BASE, encoding="utf-8")
        self.original_hash = tree_hash(inventory(self.source))
        self.store = SkillStore(root / "store")
        self.base = self.store.import_skill("fixture-core", self.source)

    def test_immutable_revision_read_and_integrity(self):
        current = self.store.revision("fixture-core")
        self.assertEqual(current["tree_hash"], self.original_hash)
        result = self.store.read_file("fixture-core", current["revision_id"], "SKILL.md")
        self.assertEqual(result["content"], (self.source / "SKILL.md").read_bytes())
        with self.assertRaises(SkillStoreError):
            self.store.read_file("fixture-core", current["revision_id"], "../secret")
        bundle = self.store._revision_dir("fixture-core", current["revision_id"]) / "bundle"
        (bundle / "SKILL.md").write_text("tamper", encoding="utf-8")
        with self.assertRaisesRegex(SkillStoreError, "revision_integrity_failure"):
            self.store.revision("fixture-core", current["revision_id"])

    def test_draft_freeze_and_separate_promotion(self):
        draft = self.store.create_draft("fixture-core", self.base["revision_id"], POLICY)
        workspace = self.store.draft_workspace(draft["draft_id"])
        (workspace / "SKILL.md").write_text(BASE + "Example: amber.\n", encoding="utf-8")
        frozen = self.store.freeze_draft(draft["draft_id"])
        self.assertTrue(frozen["promotion_eligible"])
        self.assertIn("+Example: amber.", frozen["patch"])
        self.assertFalse(frozen["promotion_performed"])
        self.assertEqual(frozen["editor_kind"], "human")
        self.assertIsNone(frozen["edit_run_id"])
        self.assertEqual(frozen["evaluation_results"], [])
        self.assertEqual(frozen["proposed_ref"]["tree_hash"],
                         frozen["proposed_tree_hash"])
        self.assertEqual(self.store.revision("fixture-core")["revision_id"],
                         self.base["revision_id"])
        promoted = self.store.promote_draft(
            draft["draft_id"], expected_base_revision=self.base["revision_id"],
            reviewed_draft_hash=frozen["proposed_tree_hash"])
        self.assertEqual(promoted["revision_id"], frozen["proposed_tree_hash"])
        self.assertEqual(self.store.revision("fixture-core")["revision_id"],
                         promoted["revision_id"])
        review_record = json.loads((self.store._draft(draft["draft_id"]) /
                                    "result.json").read_text(encoding="utf-8"))
        self.assertTrue(review_record["promotion_performed"])
        self.assertEqual(review_record["promoted_revision"], promoted["revision_id"])
        self.assertEqual(self.store.revision("fixture-core", self.base["revision_id"])[
            "tree_hash"], self.original_hash)
        self.assertEqual(tree_hash(inventory(self.source)), self.original_hash)

    def test_concurrent_base_change_blocks_second_promotion(self):
        first = self.store.create_draft("fixture-core", self.base["revision_id"], POLICY)
        second = self.store.create_draft("fixture-core", self.base["revision_id"], POLICY)
        (self.store.draft_workspace(first["draft_id"]) / "SKILL.md").write_text(
            BASE + "First.\n", encoding="utf-8")
        (self.store.draft_workspace(second["draft_id"]) / "SKILL.md").write_text(
            BASE + "Second.\n", encoding="utf-8")
        first_result = self.store.freeze_draft(first["draft_id"])
        second_result = self.store.freeze_draft(second["draft_id"])
        self.store.promote_draft(
            first["draft_id"], expected_base_revision=self.base["revision_id"],
            reviewed_draft_hash=first_result["proposed_tree_hash"])
        with self.assertRaisesRegex(ConflictError, "base_revision_changed"):
            self.store.promote_draft(
                second["draft_id"], expected_base_revision=self.base["revision_id"],
                reviewed_draft_hash=second_result["proposed_tree_hash"])

    def test_forbidden_path_and_stale_review_hash_are_rejected(self):
        draft = self.store.create_draft("fixture-core", self.base["revision_id"], POLICY)
        workspace = self.store.draft_workspace(draft["draft_id"])
        (workspace / "secret.txt").write_text("synthetic", encoding="utf-8")
        frozen = self.store.freeze_draft(draft["draft_id"])
        self.assertIn("forbidden_path", frozen["validation_errors"])
        with self.assertRaisesRegex(SkillStoreError, "draft_not_eligible"):
            self.store.promote_draft(
                draft["draft_id"], expected_base_revision=self.base["revision_id"],
                reviewed_draft_hash=frozen["proposed_tree_hash"])
        second = self.store.create_draft("fixture-core", self.base["revision_id"], POLICY)
        (self.store.draft_workspace(second["draft_id"]) / "SKILL.md").write_text(
            BASE + "Allowed.\n", encoding="utf-8")
        second_result = self.store.freeze_draft(second["draft_id"])
        with self.assertRaisesRegex(ConflictError, "reviewed_ref_mismatch"):
            self.store.promote_draft(
                second["draft_id"], expected_base_revision=self.base["revision_id"],
                reviewed_draft_hash=self.base["tree_hash"])
        self.assertTrue(second_result["promotion_eligible"])

    def test_policy_and_revision_paths_fail_closed(self):
        bad = json.loads(json.dumps(POLICY))
        bad["allowed_paths"].append("../escape.md")
        with self.assertRaisesRegex(SkillStoreError, "unsafe_relative_path"):
            self.store.create_draft("fixture-core", self.base["revision_id"], bad)
        bad = json.loads(json.dumps(POLICY))
        bad["allowed_paths"].append("scripts/run.py")
        with self.assertRaisesRegex(SkillStoreError, "policy_grants_disallowed_scripts"):
            self.store.create_draft("fixture-core", self.base["revision_id"], bad)
        with self.assertRaisesRegex(SkillStoreError, "invalid_revision_id"):
            self.store.revision("fixture-core", "../../outside")

    def test_frozen_bytes_and_policy_are_checked_again_at_promotion(self):
        draft = self.store.create_draft("fixture-core", self.base["revision_id"], POLICY)
        (self.store.draft_workspace(draft["draft_id"]) / "SKILL.md").write_text(
            BASE + "Allowed.\n", encoding="utf-8")
        frozen = self.store.freeze_draft(draft["draft_id"])
        draft_dir = self.store._draft(draft["draft_id"])
        (draft_dir / "frozen" / "SKILL.md").write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(SkillStoreError, "frozen_draft_integrity_failure"):
            self.store.promote_draft(
                draft["draft_id"], expected_base_revision=self.base["revision_id"],
                reviewed_draft_hash=frozen["proposed_tree_hash"])
        (draft_dir / "frozen" / "SKILL.md").write_bytes(
            (draft_dir / "workspace" / "SKILL.md").read_bytes())
        changed_policy = json.loads((draft_dir / "policy.json").read_text(encoding="utf-8"))
        changed_policy["max_files"] = 3
        (draft_dir / "policy.json").write_text(json.dumps(changed_policy), encoding="utf-8")
        with self.assertRaisesRegex(SkillStoreError, "policy_integrity_failure"):
            self.store.promote_draft(
                draft["draft_id"], expected_base_revision=self.base["revision_id"],
                reviewed_draft_hash=frozen["proposed_tree_hash"])

    def test_store_refuses_git_tree_before_creation(self):
        root = Path(self.temporary.name) / "repo"
        (root / ".git").mkdir(parents=True)
        target = root / "private-store"
        with self.assertRaisesRegex(SkillStoreError, "store_inside_git_tree"):
            SkillStore(target)
        self.assertFalse(target.exists())

    def test_import_rejects_source_overlapping_store(self):
        nested = self.store.root / "nested-source"
        nested.mkdir()
        (nested / "SKILL.md").write_text(BASE, encoding="utf-8")
        with self.assertRaisesRegex(SkillStoreError, "source_overlaps_store"):
            self.store.import_skill("another-skill", nested)
        with self.assertRaisesRegex(SkillStoreError, "source_overlaps_store"):
            self.store.import_skill("another-skill", Path(self.temporary.name))


if __name__ == "__main__":
    unittest.main()
