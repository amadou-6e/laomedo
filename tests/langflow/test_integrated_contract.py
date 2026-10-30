"""Native imported simplified graph, fake runner only."""

from copy import deepcopy
import json
from pathlib import Path
import unittest
from test_workgraph_demo import run_case
from test_workgraph_demo import records

FLOW = (
    Path(__file__).resolve().parents[2] / "examples/langflow-contract-routing/flow.json"
)


class IntegratedContractTests(unittest.IsolatedAsyncioTestCase):
    def flow(self):
        return json.loads(FLOW.read_text(encoding="utf-8"))

    async def case(self, submission, expected, **kwargs):
        result, calls = await run_case(submission, flow_payload=self.flow(), **kwargs)
        rows = records(result)
        self.assertEqual([row["destination"] for row in rows], [expected])
        self.assertEqual(len(calls), 1)
        self.assertIsNotNone(calls[0]["payload"]["output_requirements"])
        if expected != "success":
            self.assertIsNone(rows[0]["publication"])
        return rows, calls

    async def test_success_and_failure(self):
        for outcome in ["success", "failure"]:
            await self.case({"task_outcome": outcome, "report": "fixture"}, outcome)

    async def test_invalid_completed_output_rejects(self):
        await self.case({"task_outcome": "success"}, "rejection")

    async def test_absent_output_and_incomplete_execution_recovers(self):
        await self.case(None, "recovery", status="interrupted")

    async def test_complete_claim_without_evidence_recovers(self):
        await self.case(
            {"task_outcome": "success", "report": "fixture"},
            "recovery",
            evidence_complete=False,
        )

    async def test_requirements_mismatch_rejects(self):
        await self.case(
            {"task_outcome": "success", "report": "fixture"},
            "rejection",
            revision_override="sha256:" + "b" * 64,
        )

    async def test_native_precheck_feedback_within_one_dispatch(self):
        _, calls = await self.case(
            {"task_outcome": "success"}, "success", correction="within_request"
        )
        self.assertEqual(
            [x["contract_status"] for x in calls[0]["fixture_prechecks"]],
            ["rejected", "accepted"],
        )

    def test_export_has_one_contract_and_no_backward_edge(self):
        flow = self.flow()
        self.assertNotIn("requirements", [n["id"] for n in flow["data"]["nodes"]])
        self.assertNotIn("routing", [n["id"] for n in flow["data"]["nodes"]])
        self.assertEqual(len(flow["data"]["nodes"]), 8)
        self.assertFalse(
            any(
                e["target"] == "agent" and e["source"] == "contract"
                for e in flow["data"]["edges"]
            )
        )

    async def test_two_contracts_refuse_before_runner_call(self):
        from unittest.mock import patch
        from lfx.graph.graph.base import Graph

        flow = self.flow()
        contract = deepcopy(
            next(n for n in flow["data"]["nodes"] if n["id"] == "contract")
        )
        contract["id"] = contract["data"]["id"] = "second"
        flow["data"]["nodes"].append(contract)
        e = deepcopy(
            next(e for e in flow["data"]["edges"] if e["target"] == "contract")
        )
        e["id"] = "agent-second"
        e["target"] = "second"
        e["data"]["targetHandle"]["id"] = "second"
        e["targetHandle"] = json.dumps(e["data"]["targetHandle"])
        flow["data"]["edges"].append(e)
        with patch("urllib.request.urlopen") as http:
            with self.assertRaisesRegex(
                Exception, "ambiguous_downstream_output_contract"
            ):
                await Graph.from_payload(flow).arun(inputs=[{}], outputs=["success"])
        http.assert_not_called()

    async def test_pre_turn_failure_routes_recovery_without_publication(self):
        from unittest.mock import patch
        from lfx.graph.graph.base import Graph

        result = None
        with (
            patch.dict(
                "os.environ", {"LAOMEDO_RUNNER_TOKEN_FILE": "/absent-fixture-token"}
            ),
            patch("urllib.request.urlopen") as http,
        ):
            result = await Graph.from_payload(self.flow()).arun(
                inputs=[{}], outputs=["success", "failure", "rejection", "recovery"]
            )
        self.assertEqual([r["destination"] for r in records(result)], ["recovery"])
        self.assertIsNone(records(result)[0]["publication"])
        http.assert_not_called()

    async def test_contract_edit_after_freeze_rejects_without_new_dispatch(self):
        def edit(graph, payload, result):
            form = {
                "schema_version": 1,
                "fields": [{"name": "other", "type": "string", "required": True}],
            }
            graph.get_vertex("contract").update_raw_params(
                {"requirements_json": json.dumps(form)}
            )

        rows, calls = await self.case(
            {"task_outcome": "success", "report": "fixture"},
            "rejection",
            response_hook=edit,
        )
        self.assertEqual(
            rows[0]["routed"]["validation"]["errors"][0]["code"],
            "requirements_revision_mismatch",
        )

    async def test_model_cannot_promote_executor_or_evidence_fields(self):
        await self.case(
            {
                "task_outcome": "success",
                "report": "fixture",
                "executor_status": "completed",
                "evidence_complete": True,
            },
            "recovery",
            status="interrupted",
            evidence_complete=False,
        )

    def test_new_export_shows_only_four_route_ports_and_current_source(self):
        import importlib.util

        path = FLOW.with_name("build_flow.py")
        spec = importlib.util.spec_from_file_location("simplified_export", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        flow = self.flow()
        self.assertEqual(flow, module.build())
        contract = next(n for n in flow["data"]["nodes"] if n["id"] == "contract")
        self.assertEqual(
            [o["name"] for o in contract["data"]["node"]["outputs"]],
            ["success", "failure", "rejection", "recovery"],
        )
