"""Independent old-writer journal and comparison contracts; no model dispatch."""

import json
import sqlite3
import unittest
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID
from laomedo.skills.operations.models import SkillCommit
from laomedo.skills.operations.service import SkillOperations
from test_skills.test_operations.utils import make_operation_case


class SkillCommitPreimageTests(unittest.TestCase):
    def test_comparison_matches_the_original_public_payload_and_key_order(self):
        expected = json.loads(
            (Path(__file__).parent / "data/comparison.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as directory:
            case = make_operation_case(Path(directory))
            # Retain an independently specified legacy journal root. New imports
            # now have their own file-bearing initial commit; this assertion
            # protects the persisted old comparison contract rather than replacing
            # its golden record with a newly generated import.
            legacy = dict(expected["base_commit"])
            legacy_id = legacy.pop("commit_id")
            legacy["patch"] = ""
            with case.service.connect() as db:
                db.execute(
                    "INSERT INTO commits VALUES (?,?,?)",
                    (legacy_id, "internal-test", json.dumps(legacy)),
                )
                db.execute(
                    "INSERT INTO heads VALUES (?,?)", ("internal-test", legacy_id)
                )
            clock = SimpleNamespace(
                now=lambda *_: datetime(2026, 10, 30, tzinfo=timezone.utc)
            )
            with (
                patch("laomedo.skills.operations.service.datetime", clock),
                patch(
                    "laomedo.skills.operations.service.uuid4",
                    return_value=UUID("33333333-3333-4333-8333-333333333333"),
                ),
            ):
                reservation = case.prepare()
                with patch(
                    "laomedo.skills.registry.store.uuid4",
                    return_value=UUID("44444444-4444-4444-8444-444444444444"),
                ):
                    result = case.service.apply(
                        reservation["ticket"],
                        case.operation,
                        {"kind": "agent", "run_id": "run-id", "trace_ref": "trace-ref"},
                    )
            actual = case.service.compare(
                "internal-test",
                reservation["base_commit"],
                result["skill"]["revision_id"],
            )
        self.assertEqual(actual, expected)
        self.assertEqual(json.dumps(actual), json.dumps(expected))
        self.assertNotIn("patch", actual["base_commit"])

    def test_legacy_import_and_agent_edit_keep_exact_writer_ids_and_field_order(self):
        cases = [
            (
                "legacy-import",
                "sha256:440cb8a4f88d33fa53faa1c674ffaf1e3c4aaa8dcf7e789a2b0c18e6f5cf5ae5",
                {
                    "skill_id": "internal-test",
                    "revision_id": "sha256:9bc28aa48cce16a80d467f317ae12f1aa105c27e5ec7b1fcabeed79eb661eab5",
                    "parent_commit": None,
                    "created_at": "2026-10-30T00:00:00+00:00",
                    "message": "Import existing immutable skill",
                    "files": [],
                    "patch": "",
                    "editor": {"kind": "import"},
                    "nonce": "33333333333343338333333333333333",
                },
            ),
            (
                "agent-edit",
                "sha256:24b72a8cff13c90f21a4f51e3327ff3141e5c69ab343c5da0cc065d6976947d3",
                {
                    "skill_id": "internal-test",
                    "revision_id": "sha256:163e67ec748cd983e269c180fbf9884fba1a977669285ea28feadc95816e32ac",
                    "parent_commit": "sha256:440cb8a4f88d33fa53faa1c674ffaf1e3c4aaa8dcf7e789a2b0c18e6f5cf5ae5",
                    "created_at": "2026-10-30T00:00:00+00:00",
                    "message": "Change two files together",
                    "files": ["SKILL.md", "rules/one.md"],
                    "patch": "--- base/SKILL.md\n"
                    "+++ draft/SKILL.md\n"
                    "@@ -2,3 +2,5 @@\n"
                    " name: internal-test\\n\n"
                    " description: Internal unit fixture.\\n\n"
                    " ---\\n\n"
                    "+\\n\n"
                    "+Updated.\\n\n"
                    "--- base/rules/one.md\n"
                    "+++ draft/rules/one.md\n"
                    "@@ -1 +1 @@\n"
                    "-original\\n\n"
                    "+updated\\n\n",
                    "editor": {
                        "kind": "agent",
                        "run_id": "run-id",
                        "trace_ref": "trace-ref",
                    },
                    "draft_id": "44444444-4444-4444-8444-444444444444",
                    "policy_ref": {
                        "policy_id": "test-policy",
                        "revision_id": "1",
                        "hash": "sha256:32cf3a983e902fd4f5802aa4bec03ef4a9cddb2fba929f22e0c946c42ebf8301",
                    },
                    "nonce": "33333333333343338333333333333333",
                },
            ),
        ]
        for name, identity, record in cases:
            with self.subTest(writer=name), sqlite3.connect(":memory:") as db:
                db.execute(
                    "CREATE TABLE commits(id TEXT PRIMARY KEY, skill TEXT, record TEXT)"
                )
                db.execute("CREATE TABLE heads(skill TEXT PRIMARY KEY, id TEXT)")
                service = SkillOperations.__new__(SkillOperations)
                result = service._commit(db, SkillCommit.model_validate(record))
                self.assertEqual(result.commit_id, identity)
                self.assertEqual(result.to_payload(), {"commit_id": identity, **record})
                self.assertEqual(list(result.to_payload()), ["commit_id", *record])
                self.assertEqual(
                    db.execute(
                        "SELECT record FROM commits WHERE id=?", (identity,)
                    ).fetchone()[0],
                    json.dumps(record),
                )
                self.assertEqual(
                    db.execute(
                        "SELECT id FROM heads WHERE skill=?", (record["skill_id"],)
                    ).fetchone()[0],
                    identity,
                )
