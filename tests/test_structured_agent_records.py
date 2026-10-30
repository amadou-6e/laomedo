"""Internal compatibility evidence; these controls never invoke real agents."""

import json
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import UUID
from laomedo.agents.interface.models import AgentRunReference, RunnerStatusRecord
from laomedo.agents.orchestration.utils import envelope
from laomedo.agents.interface.bridge import HttpAgentBridge
from laomedo.agents.workspaces.utils import _hash_tree


class StructuredAgentRecordsTests(unittest.TestCase):
    def test_preparation_bytes_and_existing_reader_match_baseline(self):
        from test_local_runner import LocalRunnerTests
        cases = json.loads((Path(__file__).parent / "contracts/agent-records-a9317f6.json").read_text(encoding="utf-8"))
        for with_skill in (False, True):
            with self.subTest(skill=with_skill):
                case = LocalRunnerTests()
                case.setUp()
                try:
                    (case.skill_source / "SKILL.md").write_bytes(b"---\nname: sample\n---\nUse amber.\n")
                    case.revision = case.runner.store._store_revision("sample", case.skill_source, None)
                    case.runner.instance_id = "instance-id"
                    request = case.request()
                    if not with_skill:
                        request.pop("skill_ref")
                    with patch("laomedo.agents.agents.base.agent.uuid4", return_value=UUID("55555555-5555-4555-8555-555555555555")):
                        result = case.runner._prepare(request, client_request_id="request-id", request_hash="sha256:" + "1" * 64)
                    expected = dict(cases["prepared_skill" if with_skill else "prepared_empty"])
                    # File-only preparation includes private Git metadata. Its
                    # hooksPath names a random isolated home, so independently
                    # recompute only this observed hash; do not freeze a temp path.
                    expected["effective_hash"] = _hash_tree(case.runner._run_dir(result["run_id"]) / "workspace")
                    self.assertEqual(result, expected)
                    self.assertEqual(list(result), list(expected))
                    self.assertEqual(case.runner.status(result["run_id"]), expected)
                    self.assertEqual(json.dumps(result, sort_keys=True, separators=(",", ":")), json.dumps(expected, sort_keys=True, separators=(",", ":")))
                finally:
                    case.doCleanups()

    def test_unknown_evidence_and_join_shapes_match_old_presenters(self):
        cases = json.loads((Path(__file__).parent / "contracts/agent-records-a9317f6.json").read_text(encoding="utf-8"))
        for case in cases["references"]:
            result = AgentRunReference.from_runner_status(case["input"], provider="codex").to_payload()
            self.assertEqual(result, case["expected"])
            self.assertEqual(list(result), list(case["expected"]))
        result = RunnerStatusRecord.from_snapshot(cases["join"]["input"], provider="codex").to_payload()
        self.assertEqual(result, cases["join"]["expected"])
        self.assertEqual(list(result), list(cases["join"]["expected"]))
        self.assertEqual(RunnerStatusRecord.from_snapshot(None, provider="codex").to_payload(), {"status": "pending_start"})

    def test_handoff_and_request_hash_preimages_match_baseline(self):
        cases = json.loads((Path(__file__).parent / "contracts/structured-data-a9317f6.json").read_text(encoding="utf-8"))
        with patch("laomedo.agents.orchestration.utils.uuid4", return_value="22222222-2222-4222-8222-222222222222"):
            result = envelope(None, {"provider": "codex", "model": "model", "effort": "low"}, "Read only.", skills=[])
        self.assertEqual(result, cases["handoff"])
        request, digest = HttpAgentBridge.fresh_request(result, "request-id")
        self.assertEqual(request, cases["request"]["payload"])
        self.assertEqual(digest, cases["request"]["digest"])
        self.assertEqual(json.dumps({k: v for k, v in request.items() if k != "request_id"}, sort_keys=True, separators=(",", ":"), ensure_ascii=False), cases["request"]["preimage"])
