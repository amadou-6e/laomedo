"""Literal wire projections, independent of the current serializer."""

import json
from pathlib import Path
import unittest
from laomedo.agents.interface.models import AgentRunReference, RunnerStatusRecord


class AgentReferenceRecordTests(unittest.TestCase):
    def test_unknown_evidence_and_join_shapes_match_old_presenters(self):
        cases = json.loads(
            (Path(__file__).parent / "data/status-records.json").read_text(
                encoding="utf-8"
            )
        )
        for case in cases["references"]:
            with self.subTest(status=case["input"].get("status")):
                result = AgentRunReference.from_runner_status(
                    case["input"], provider="codex"
                ).to_payload()
                self.assertEqual(result, case["expected"])
                self.assertEqual(list(result), list(case["expected"]))
        result = RunnerStatusRecord.from_snapshot(
            cases["join"]["input"], provider="codex"
        ).to_payload()
        self.assertEqual(result, cases["join"]["expected"])
        self.assertEqual(list(result), list(cases["join"]["expected"]))
        self.assertEqual(
            RunnerStatusRecord.from_snapshot(None, provider="codex").to_payload(),
            {"status": "pending_start"},
        )
