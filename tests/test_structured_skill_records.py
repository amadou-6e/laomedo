"""Internal byte/hash compatibility controls captured before writer migration."""

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import UUID
from laomedo.skills.registry.store import SkillStore


class StructuredSkillRecordsTests(unittest.TestCase):
    def test_revision_draft_and_frozen_record_match_old_writers(self):
        from test_skill_store import SkillStoreTests, POLICY, BASE

        expected = json.loads(
            (
                Path(__file__).parent / "contracts/structured-data-a9317f6.json"
            ).read_text(encoding="utf-8")
        )["skill"]
        case = SkillStoreTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        self.assertEqual(case.base, expected["revision"])
        with patch(
            "laomedo.skills.registry.store.uuid4",
            return_value=UUID("11111111-1111-4111-8111-111111111111"),
        ):
            draft = case.store.create_draft(
                "fixture-core", case.base["revision_id"], POLICY
            )
        self.assertEqual(draft, expected["draft"])
        (case.store.draft_workspace(draft["draft_id"]) / "SKILL.md").write_text(
            BASE + "Example: amber.\n", encoding="utf-8"
        )
        frozen = case.store.freeze_draft(draft["draft_id"])
        self.assertEqual(frozen, expected["frozen"])
        self.assertEqual(list(frozen), list(expected["frozen"]))
        self.assertEqual(
            list(frozen["policy_ref"]), list(expected["frozen"]["policy_ref"])
        )
        self.assertEqual(
            SkillStore(case.store.root).revision("fixture-core"), expected["revision"]
        )
        # Existing readers continue tolerating historical extension fields.
        path = (
            case.store._revision_dir("fixture-core", case.base["revision_id"])
            / "record.json"
        )
        path.write_text(
            json.dumps({**case.base, "historical_extension": {"version": 2}}),
            encoding="utf-8",
        )
        self.assertEqual(
            case.store.revision("fixture-core")["historical_extension"], {"version": 2}
        )

    def test_commit_id_preimages_and_comparison_match_old_writers(self):
        from test_skill_operations import SkillOperationTests

        expected = json.loads(
            (Path(__file__).parent / "contracts/skill-commits-a9317f6.json").read_text(
                encoding="utf-8"
            )
        )
        case = SkillOperationTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
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
            imported = case.service.diff("internal-test", reservation["base_commit"])
            self.assertEqual(imported, expected["import"])
            self.assertNotIn("draft_id", imported)
            self.assertNotIn("policy_ref", imported)
            with patch(
                "laomedo.skills.registry.store.uuid4",
                return_value=UUID("44444444-4444-4444-8444-444444444444"),
            ):
                result = case.service.apply(
                    reservation["ticket"],
                    case.operation,
                    {"kind": "agent", "run_id": "run-id", "trace_ref": "trace-ref"},
                )
        self.assertEqual(result, expected["result"])
        self.assertEqual(
            case.service.apply(reservation["ticket"], case.operation), result
        )
        self.assertEqual(list(result["commit"]), list(expected["result"]["commit"]))
        self.assertNotIn("thread_id", result["commit"]["editor"])
        self.assertEqual(
            case.service.compare(
                "internal-test", imported["commit_id"], result["skill"]["revision_id"]
            ),
            expected["comparison"],
        )
