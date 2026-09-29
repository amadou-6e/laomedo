import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from laomedo.skill_store import (ConflictError, SkillStore, SkillStoreError,
                                 inventory, tree_hash, validate_policy)


BASE = ("---\nname: fixture-core\ndescription: Synthetic skill.\n---\n\n"
        "Rule: answer amber.\n")
POLICY = {
    "policy_id": "fixture-core-policy", "revision_id": "1",
    "allowed_paths": ["SKILL.md", "examples/amber.md"],
    "allowed_suffixes": [".md"], "allow_new_files": True,
    "allow_deletions": False,
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
        (self.source / "SKILL.md").write_bytes(BASE.encode("utf-8"))
        self.original_hash = tree_hash(inventory(self.source))
        self.store = SkillStore(root / "store")
        self.base = self.store.import_skill("fixture-core", self.source)
        self.policy_hash = validate_policy(POLICY)["hash"]

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
            reviewed_draft_hash=frozen["proposed_tree_hash"],
            expected_policy_hash=self.policy_hash)
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
            reviewed_draft_hash=first_result["proposed_tree_hash"],
            expected_policy_hash=self.policy_hash)
        with self.assertRaisesRegex(ConflictError, "base_revision_changed"):
            self.store.promote_draft(
                second["draft_id"], expected_base_revision=self.base["revision_id"],
                reviewed_draft_hash=second_result["proposed_tree_hash"],
                expected_policy_hash=self.policy_hash)

    def test_forbidden_path_and_stale_review_hash_are_rejected(self):
        draft = self.store.create_draft("fixture-core", self.base["revision_id"], POLICY)
        workspace = self.store.draft_workspace(draft["draft_id"])
        (workspace / "secret.txt").write_text("synthetic", encoding="utf-8")
        frozen = self.store.freeze_draft(draft["draft_id"])
        self.assertIn("forbidden_path", frozen["validation_errors"])
        self.assertIsNone(frozen["proposed_ref"])
        self.assertFalse((self.store._draft(draft["draft_id"]) / "frozen").exists())
        with self.assertRaisesRegex(SkillStoreError, "draft_not_eligible"):
            self.store.promote_draft(
                draft["draft_id"], expected_base_revision=self.base["revision_id"],
                reviewed_draft_hash=frozen["proposed_tree_hash"],
                expected_policy_hash=self.policy_hash)
        second = self.store.create_draft("fixture-core", self.base["revision_id"], POLICY)
        (self.store.draft_workspace(second["draft_id"]) / "SKILL.md").write_text(
            BASE + "Allowed.\n", encoding="utf-8")
        second_result = self.store.freeze_draft(second["draft_id"])
        with self.assertRaisesRegex(ConflictError, "reviewed_ref_mismatch"):
            self.store.promote_draft(
                second["draft_id"], expected_base_revision=self.base["revision_id"],
                reviewed_draft_hash=self.base["tree_hash"],
                expected_policy_hash=self.policy_hash)
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
                reviewed_draft_hash=frozen["proposed_tree_hash"],
                expected_policy_hash=self.policy_hash)
        (draft_dir / "frozen" / "SKILL.md").write_bytes(
            (self.store._workspace(draft["draft_id"]) / "SKILL.md").read_bytes())
        changed_policy = json.loads((draft_dir / "policy.json").read_text(encoding="utf-8"))
        changed_policy["max_files"] = 3
        (draft_dir / "policy.json").write_text(json.dumps(changed_policy), encoding="utf-8")
        with self.assertRaisesRegex(SkillStoreError, "policy_integrity_failure"):
            self.store.promote_draft(
                draft["draft_id"], expected_base_revision=self.base["revision_id"],
                reviewed_draft_hash=frozen["proposed_tree_hash"],
                expected_policy_hash=self.policy_hash)

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

    def test_patch_shows_exact_line_endings_and_rejects_non_utf8(self):
        draft = self.store.create_draft("fixture-core", self.base["revision_id"], POLICY)
        workspace = self.store.draft_workspace(draft["draft_id"])
        (workspace / "SKILL.md").write_bytes(BASE.replace("\n", "\r\n").encode())
        result = self.store.freeze_draft(draft["draft_id"])
        self.assertTrue(result["promotion_eligible"])
        self.assertIn("\\r\\n", result["patch"])
        self.assertIn("\\n", result["patch"])
        self.assertNotEqual(result["patch"], "")
        patches = []
        for value in (b"\xff", b"\xfe"):
            other = self.store.create_draft("fixture-core", self.base["revision_id"],
                                            POLICY)
            (self.store.draft_workspace(other["draft_id"]) / "SKILL.md").write_bytes(
                BASE.encode() + value)
            rejected = self.store.freeze_draft(other["draft_id"])
            self.assertIn("non_utf8_changed_file", rejected["validation_errors"])
            self.assertIsNone(rejected["proposed_ref"])
            patches.append(rejected["patch"])
        self.assertNotEqual(patches[0], patches[1])

    def test_policy_hash_is_bound_to_promotion_even_if_records_change(self):
        draft = self.store.create_draft("fixture-core", self.base["revision_id"], POLICY)
        (self.store.draft_workspace(draft["draft_id"]) / "SKILL.md").write_text(
            BASE + "Allowed.\n", encoding="utf-8")
        result = self.store.freeze_draft(draft["draft_id"])
        folder = self.store._draft(draft["draft_id"])
        wider = json.loads(json.dumps(POLICY))
        wider["allow_deletions"] = True
        (folder / "policy.json").write_text(json.dumps(wider), encoding="utf-8")
        record = json.loads((folder / "record.json").read_text(encoding="utf-8"))
        record["policy_ref"] = validate_policy(wider)
        (folder / "record.json").write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaisesRegex(ConflictError, "reviewed_ref_mismatch"):
            self.store.promote_draft(
                draft["draft_id"], expected_base_revision=self.base["revision_id"],
                reviewed_draft_hash=result["proposed_tree_hash"],
                expected_policy_hash=self.policy_hash)

    def test_revert_records_actual_promotion_and_recovers_result(self):
        first = self.store.create_draft("fixture-core", self.base["revision_id"], POLICY)
        (self.store.draft_workspace(first["draft_id"]) / "SKILL.md").write_text(
            BASE + "New.\n", encoding="utf-8")
        first_result = self.store.freeze_draft(first["draft_id"])
        revision_b = self.store.promote_draft(
            first["draft_id"], expected_base_revision=self.base["revision_id"],
            reviewed_draft_hash=first_result["proposed_tree_hash"],
            expected_policy_hash=self.policy_hash)
        second = self.store.create_draft("fixture-core", revision_b["revision_id"],
                                         POLICY)
        (self.store.draft_workspace(second["draft_id"]) / "SKILL.md").write_bytes(
            BASE.encode("utf-8"))
        second_result = self.store.freeze_draft(second["draft_id"])
        revision_a = self.store.promote_draft(
            second["draft_id"], expected_base_revision=revision_b["revision_id"],
            reviewed_draft_hash=second_result["proposed_tree_hash"],
            expected_policy_hash=self.policy_hash)
        self.assertEqual(revision_a["revision_id"], self.base["revision_id"])
        log = (self.store._skill("fixture-core") / "promotions" /
               (second["draft_id"] + ".json"))
        entry = json.loads(log.read_text(encoding="utf-8"))
        self.assertEqual(entry["base_revision"], revision_b["revision_id"])
        self.assertEqual(entry["promoted_revision"], revision_a["revision_id"])
        log.unlink()
        result_path = self.store._draft(second["draft_id"]) / "result.json"
        unfinished = json.loads(result_path.read_text(encoding="utf-8"))
        unfinished["promotion_performed"] = False
        unfinished.pop("promoted_revision")
        result_path.write_text(json.dumps(unfinished), encoding="utf-8")
        self.store.promote_draft(
            second["draft_id"], expected_base_revision=revision_b["revision_id"],
            reviewed_draft_hash=second_result["proposed_tree_hash"],
            expected_policy_hash=self.policy_hash)
        repaired = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertTrue(repaired["promotion_performed"])
        self.assertTrue(log.is_file())

    def test_workspace_is_outside_store_and_hardlinks_are_rejected(self):
        draft = self.store.create_draft("fixture-core", self.base["revision_id"], POLICY)
        workspace = self.store.draft_workspace(draft["draft_id"])
        self.assertFalse(workspace.is_relative_to(self.store.root))
        outside = Path(self.temporary.name) / "outside.md"
        outside.write_bytes(BASE.encode("utf-8"))
        file = workspace / "SKILL.md"
        file.unlink()
        os.link(outside, file)
        result = self.store.freeze_draft(draft["draft_id"])
        self.assertIn("hardlinked_file", result["validation_errors"])
        self.assertIsNone(result["proposed_ref"])

    def test_interrupted_freeze_reuses_matching_frozen_copy(self):
        draft = self.store.create_draft("fixture-core", self.base["revision_id"], POLICY)
        workspace = self.store.draft_workspace(draft["draft_id"])
        (workspace / "SKILL.md").write_text(BASE + "Allowed.\n", encoding="utf-8")
        shutil.copytree(workspace, self.store._draft(draft["draft_id"]) / "frozen")
        result = self.store.freeze_draft(draft["draft_id"])
        self.assertTrue(result["promotion_eligible"])

    def test_conflicting_freeze_and_busy_locks_fail_with_typed_conflicts(self):
        draft = self.store.create_draft("fixture-core", self.base["revision_id"], POLICY)
        workspace = self.store.draft_workspace(draft["draft_id"])
        (workspace / "SKILL.md").write_text(BASE + "Allowed.\n", encoding="utf-8")
        frozen = self.store._draft(draft["draft_id"]) / "frozen"
        shutil.copytree(workspace, frozen)
        (frozen / "SKILL.md").write_text(BASE + "Different.\n", encoding="utf-8")
        with self.assertRaisesRegex(ConflictError, "interrupted_freeze_conflict"):
            self.store.freeze_draft(draft["draft_id"])
        (frozen / "SKILL.md").write_bytes((workspace / "SKILL.md").read_bytes())
        result = self.store.freeze_draft(draft["draft_id"])
        lock = self.store._skill("fixture-core") / "promotion.lock"
        lock.write_text("busy", encoding="utf-8")
        with self.assertRaisesRegex(ConflictError, "promotion_busy"):
            self.store.promote_draft(
                draft["draft_id"], expected_base_revision=self.base["revision_id"],
                reviewed_draft_hash=result["proposed_tree_hash"],
                expected_policy_hash=self.policy_hash)
        lock.unlink()
        another = self.store._skill("another")
        another.mkdir()
        (another / "import.lock").write_text("busy", encoding="utf-8")
        with self.assertRaisesRegex(ConflictError, "import_busy"):
            self.store.import_skill("another", self.source)

    def test_deletion_scripts_and_empty_frontmatter_are_rejected(self):
        bad = json.loads(json.dumps(POLICY))
        bad["allow_assets"] = True
        for suffix in (".cmd", ".mjs", ".rb"):
            bad["allowed_paths"] = ["SKILL.md", "hook" + suffix]
            bad["allowed_suffixes"] = [".md", suffix]
            with self.assertRaisesRegex(SkillStoreError,
                                        "policy_grants_disallowed_scripts"):
                validate_policy(bad)
        allowed_script = json.loads(json.dumps(POLICY))
        allowed_script["allow_scripts"] = True
        allowed_script["allowed_paths"] = ["SKILL.md", "scripts/run.py"]
        allowed_script["allowed_suffixes"] = [".md", ".py"]
        self.assertIn("hash", validate_policy(allowed_script))
        empty = self.store.create_draft("fixture-core", self.base["revision_id"],
                                        POLICY)
        (self.store.draft_workspace(empty["draft_id"]) / "SKILL.md").write_text(
            BASE.replace("name: fixture-core", "name: "), encoding="utf-8")
        self.assertIn("frontmatter_field_missing",
                      self.store.freeze_draft(empty["draft_id"])["validation_errors"])
        added = self.store.create_draft("fixture-core", self.base["revision_id"], POLICY)
        (self.store.draft_workspace(added["draft_id"]) / "examples").mkdir()
        (self.store.draft_workspace(added["draft_id"]) / "examples" /
         "amber.md").write_text("Synthetic.\n", encoding="utf-8")
        added_result = self.store.freeze_draft(added["draft_id"])
        with_example = self.store.promote_draft(
            added["draft_id"], expected_base_revision=self.base["revision_id"],
            reviewed_draft_hash=added_result["proposed_tree_hash"],
            expected_policy_hash=self.policy_hash)
        removed = self.store.create_draft("fixture-core", with_example["revision_id"],
                                          POLICY)
        (self.store.draft_workspace(removed["draft_id"]) / "examples" /
         "amber.md").unlink()
        (self.store.draft_workspace(removed["draft_id"]) / "examples").rmdir()
        self.assertIn("deletion_forbidden",
                      self.store.freeze_draft(removed["draft_id"])["validation_errors"])

    @unittest.skipUnless(sys.platform == "win32", "Windows junction only")
    def test_windows_junction_to_outside_tree_is_rejected(self):
        draft = self.store.create_draft("fixture-core", self.base["revision_id"], POLICY)
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        (outside / "amber.md").write_text("External.\n", encoding="utf-8")
        junction = self.store.draft_workspace(draft["draft_id"]) / "examples"
        made = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction),
                               str(outside)], capture_output=True, text=True)
        if made.returncode:
            self.skipTest("junction creation unavailable")
        try:
            result = self.store.freeze_draft(draft["draft_id"])
            self.assertIn("linked_path", result["validation_errors"])
            self.assertIsNone(result["proposed_ref"])
        finally:
            junction.rmdir()


if __name__ == "__main__":
    unittest.main()
