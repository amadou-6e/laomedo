"""Compare current preparation and status reads to independent wire records."""

import json
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import UUID
from laomedo.agents.workspaces.utils import _hash_tree
from test_agents.test_runtime.models import RunnerCase


class PreparationRecordTests(unittest.TestCase):
    def test_preparation_bytes_and_existing_reader_match_baseline(self):
        cases = json.loads(
            (Path(__file__).parent / "data/prepared-records.json").read_text(
                encoding="utf-8"
            )
        )
        for with_skill in (False, True):
            with self.subTest(skill=with_skill):
                case = RunnerCase.create()
                self.addCleanup(case.close)
                (case.skill_source / "SKILL.md").write_bytes(
                    b"---\nname: sample\n---\nUse amber.\n"
                )
                case.revision = case.runner.store._store_revision(
                    "sample", case.skill_source, None
                )
                case.runner.instance_id = "instance-id"
                request = case.request()
                if not with_skill:
                    request.pop("skill_ref")
                with patch(
                    "laomedo.agents.agents.base.agent.uuid4",
                    return_value=UUID("55555555-5555-4555-8555-555555555555"),
                ):
                    result = case.runner._prepare(
                        request,
                        client_request_id="request-id",
                        request_hash="sha256:" + "1" * 64,
                    )
                expected = dict(
                    cases["prepared_skill" if with_skill else "prepared_empty"]
                )
                # Only the hooksPath-bearing private Git metadata is machine-specific.
                expected["effective_hash"] = _hash_tree(
                    case.runner._run_dir(result["run_id"]) / "workspace"
                )
                self.assertEqual(result, expected)
                self.assertEqual(list(result), list(expected))
                self.assertEqual(case.runner.status(result["run_id"]), expected)
                self.assertEqual(
                    json.dumps(result, sort_keys=True, separators=(",", ":")),
                    json.dumps(expected, sort_keys=True, separators=(",", ":")),
                )
