"""Import history precedes editing and retains existing journal identities."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from laomedo.skills.operations.models.provenance import ImportedSkillEditor
from laomedo.skills.operations.models.history import SkillCommit
from laomedo.skills.operations.service import SkillOperations
from laomedo.skills.registry.errors import ConflictError
from laomedo.skills.registry.errors import SkillStoreError
from laomedo.skills.registry.utils.files import write_json
from test_skills.test_operations.utils import make_operation_case


class SkillImportHistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.case = make_operation_case(Path(temporary.name))
        self.skill = "internal-test"
        self.revision = self.case.initial["revision_id"]
        self.import_path = self.case.store._skill(self.skill) / "import.json"
        self.read_only = SkillOperations(
            self.case.store, self.case.root / "read.db", {}
        )

    def test_import_is_durable_before_history_or_edit_and_lists_all_added_files(self):
        imported = json.loads(self.import_path.read_text())
        self.assertEqual(imported["origin"], "import")
        history = self.read_only.history(self.skill, self.revision)
        self.assertEqual(len(history["commits"]), 1)
        root = history["commits"][0]
        self.assertIsNone(root["parent_commit"])
        self.assertEqual(root["message"], "Initial import")
        self.assertEqual(root["created_at"], imported["recorded_at"])
        self.assertEqual(root["revision_id"], self.revision)
        self.assertEqual(root["files"], ["SKILL.md", "rules/one.md"])
        self.assertEqual(root["editor"], {"kind": "import"})
        diff = self.read_only.diff(self.skill, root["commit_id"])
        self.assertIn("+original", diff["patch"])
        self.assertIn("+---", diff["patch"])
        # The viewer compares a selected snapshot to current, not to its parent.
        self.assertEqual(
            self.read_only.compare(self.skill, root["commit_id"], self.revision)[
                "files"
            ],
            [],
        )
        with self.read_only.connect() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 0
            )
        with self.assertRaisesRegex(SkillStoreError, "skill_edit_not_authorized"):
            self.read_only.prepare(self.skill, self.revision)

    def test_history_repeated_concurrent_and_reopened_does_not_duplicate_import(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(
                pool.map(
                    lambda _: self.read_only.history(self.skill, self.revision),
                    range(12),
                )
            )
        self.assertTrue(all(result == results[0] for result in results))
        reopened = SkillOperations(self.case.store, self.read_only.database, {})
        self.assertEqual(reopened.history(self.skill, self.revision), results[0])
        # A journal can materialize the same durable import, without a new timestamp/id.
        self.assertEqual(
            self.case.service.history(self.skill, self.revision), results[0]
        )
        with reopened.connect() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM commits").fetchone()[0], 1
            )

    def test_first_edit_parents_visible_import_and_replay_keeps_two_commits(self):
        root = self.case.service.history(self.skill, self.revision)["commits"][0]
        ticket = self.case.prepare(self.revision, root["commit_id"])
        result = self.case.service.apply(ticket["ticket"], self.case.operation)
        self.assertEqual(result["commit"]["parent_commit"], root["commit_id"])
        self.assertEqual(
            self.case.service.apply(ticket["ticket"], self.case.operation), result
        )
        history = self.case.service.history(self.skill, result["skill"]["revision_id"])
        self.assertEqual(
            [item["commit_id"] for item in history["commits"]],
            [result["commit"]["commit_id"], root["commit_id"]],
        )

    def test_legacy_import_backfill_marks_unknown_date_and_is_stable(self):
        self.import_path.unlink()
        started = datetime.now(timezone.utc)
        root = self.read_only.history(self.skill, self.revision)["commits"][0]
        self.assertIn("original import time unknown", root["message"])
        self.assertGreaterEqual(datetime.fromisoformat(root["created_at"]), started)
        self.assertEqual(
            json.loads(self.import_path.read_text())["origin"], "legacy-import"
        )
        self.assertEqual(
            self.case.service.history(self.skill, self.revision)["commits"][0], root
        )
        self.assertEqual(root["files"], ["SKILL.md", "rules/one.md"])
        self.assertIn(
            "+original", self.read_only.diff(self.skill, root["commit_id"])["patch"]
        )

    def test_legacy_promoted_latest_backfill_follows_original_root(self):
        self.import_path.unlink()
        draft = self.case.store.create_draft(
            self.skill, self.revision, self.case.policy
        )
        workspace = self.case.store.draft_workspace(draft["draft_id"])
        (workspace / "rules/one.md").write_text("promoted\n")
        frozen = self.case.store.freeze_draft(draft["draft_id"])
        promoted = self.case.store.promote_draft(
            draft["draft_id"],
            expected_base_revision=self.revision,
            reviewed_draft_hash=frozen["proposed_tree_hash"],
            expected_policy_hash=frozen["policy_ref"]["hash"],
        )
        history = self.read_only.history(self.skill, promoted["revision_id"])
        self.assertEqual(len(history["commits"]), 2)
        head, root = history["commits"]
        self.assertEqual(root["revision_id"], self.revision)
        self.assertNotEqual(root["revision_id"], promoted["revision_id"])
        self.assertEqual(head["revision_id"], promoted["revision_id"])
        self.assertEqual(head["parent_commit"], root["commit_id"])
        self.assertIn("original edit time unknown", head["message"])
        self.assertIn(
            "+promoted", self.read_only.diff(self.skill, head["commit_id"])["patch"]
        )
        editable = SkillOperations(
            self.case.store, self.read_only.database, {self.skill: self.case.policy}
        )
        with self.assertRaisesRegex(ConflictError, "skill_base_changed"):
            editable.prepare(self.skill, promoted["revision_id"])
        prepared = editable.prepare(
            self.skill, promoted["revision_id"], head["commit_id"]
        )
        applied = editable.apply(prepared["ticket"], self.case.operation)
        self.assertEqual(applied["commit"]["parent_commit"], head["commit_id"])
        reopened = SkillOperations(self.case.store, self.read_only.database, {})
        self.assertEqual(
            reopened.history(self.skill, applied["skill"]["revision_id"])["commits"][
                -2:
            ],
            [head, root],
        )

    def test_existing_history_read_does_not_request_an_edit_lock(self):
        expected = self.read_only.history(self.skill, self.revision)
        with self.read_only.connect() as writer:
            writer.execute("BEGIN IMMEDIATE")
            self.assertEqual(
                self.read_only.history(self.skill, self.revision), expected
            )

    def test_existing_legacy_root_and_edit_ids_are_not_rewritten(self):
        with self.case.service.connect() as db:
            old = self.case.service._commit(
                db,
                SkillCommit(
                    skill_id=self.skill,
                    revision_id=self.revision,
                    parent_commit=None,
                    created_at="2026-01-01T00:00:00+00:00",
                    message="Import existing immutable skill",
                    files=[],
                    patch="",
                    editor=ImportedSkillEditor(),
                    nonce="old-journal-salt",
                ),
            ).to_payload()
        result = self.case.service.apply(
            self.case.prepare()["ticket"], self.case.operation
        )
        before = self.case.service.history(self.skill, result["skill"]["revision_id"])
        self.import_path.unlink()
        reopened = SkillOperations(self.case.store, self.case.service.database, {})
        self.assertEqual(
            reopened.history(self.skill, self.revision),
            dict(before, selected_revision=self.revision),
        )
        self.assertEqual(reopened.diff(self.skill, old["commit_id"]), old)
        self.assertFalse(self.import_path.exists())

    def test_invalid_revision_cursor_and_import_metadata_do_not_seed_history(self):
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.read_only.history(self.skill, "sha256:" + "0" * 64)
        with self.assertRaisesRegex(SkillStoreError, "skill_commit_unavailable"):
            self.read_only.history(self.skill, self.revision, "sha256:" + "0" * 64)
        imported = json.loads(self.import_path.read_text())
        write_json(self.import_path, dict(imported, skill_id="wrong-skill"))
        with self.assertRaisesRegex(SkillStoreError, "revision_integrity_failure"):
            self.read_only.history(self.skill, self.revision)
        with self.read_only.connect() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM commits").fetchone()[0], 0
            )

    def test_interrupted_import_retains_one_event_and_rejects_different_retry(self):
        name = "interrupted"
        source = self.case.root / "source"
        with patch(
            "laomedo.skills.registry.store.write_json",
            side_effect=self._interrupt_latest_write,
        ):
            with self.assertRaises(OSError):
                self.case.store.import_skill(name, source)
        path = self.case.store._skill(name) / "import.json"
        event = path.read_bytes()
        revisions = sorted((path.parent / "revisions").iterdir())
        content = (source / "rules/one.md").read_bytes()
        (source / "rules/one.md").write_bytes(b"different retry\n")
        with self.assertRaisesRegex(ConflictError, "skill_already_exists"):
            self.case.store.import_skill(name, source)
        self.assertFalse((path.parent / "latest.json").exists())
        self.assertEqual(path.read_bytes(), event)
        self.assertEqual(sorted((path.parent / "revisions").iterdir()), revisions)
        (source / "rules/one.md").write_bytes(content)
        self.case.store.import_skill(name, source)
        self.assertEqual(path.read_bytes(), event)
        with self.assertRaisesRegex(ConflictError, "skill_already_exists"):
            self.case.store.import_skill(name, source)

    @staticmethod
    def _interrupt_latest_write(path, record):
        """Simulate interruption after the import event but before publication."""
        if path.name == "latest.json":
            raise OSError("interrupted")
        write_json(path, record)
