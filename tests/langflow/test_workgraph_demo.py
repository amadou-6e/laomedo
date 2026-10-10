"""Execute the exported/imported graph in pinned Langflow; runner responses are fixtures."""
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from lfx.graph.graph.base import Graph

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "examples/langflow-workgraph-demo"
RUN = "aeb54b12-3ca7-43a7-97b3-762dadc94721"
HASH = "sha256:" + "a" * 64
spec = importlib.util.spec_from_file_location("demo_builder", HERE / "build_flow.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class Response(io.BytesIO):
    def __enter__(self):
        return self
    def __exit__(self, *_):
        self.close()


async def run_case(submission, *, status="completed", correction=None,
                   revision_override=None, evidence_complete=None):
    flow = json.loads((HERE / "flow.json").read_text(encoding="utf-8"))
    calls = []
    def respond(req, **_kwargs):
        payload = json.loads(req.data) if req.data else None
        call = {"method": req.get_method(), "payload": payload}
        calls.append(call)
        final = submission
        reference = payload.get("output_requirements") if payload else None
        precheck = []
        if correction:
            from laomedo.output_contract import precheck_response
            for candidate in [submission, {"task_outcome": "success", "report": "corrected fixture"}] if correction == "within_request" else [submission, submission]:
                feedback = precheck_response(reference, {"tool": "laomedo_output_precheck", "threadId": "fixture-thread",
                    "arguments": {"requirements_revision": reference["requirements_revision"], "submission": candidate}}, "fixture-thread")
                precheck.append(json.loads(feedback["contentItems"][0]["text"]))
                final = candidate
            call["fixture_prechecks"] = precheck
            call["fixture_continuations"] = 0 if correction == "within_request" else 1
            call["evidence_source"] = "fixture_runner_script"
        result = {"run_id": RUN, "status": status, "answer": json.dumps(final),
                  "thread_id": "fixture-thread", "post_run_hash": HASH,
                  "raw_event_ref": f"laomedo:run:{RUN}:events",
                  "invocation_id": "fixture-invocation", "trace_id": "fixture-trace",
                  "evidence_complete": status == "completed" if evidence_complete is None else evidence_complete,
                  "client_request_id": payload.get("request_id") if payload else None}
        if reference:
            result["requirements_revision"] = revision_override or reference["requirements_revision"]
            result["precheck"] = {"installed": True, "call_count": len(precheck)}
        result["skill"] = {"revision_id": payload["skill_ref"]["revision_id"], "use_evidence": "fixture_offered"}
        if status != "completed":
            result["error_category"] = "fixture_runtime_interruption"
            result["output_ref"] = "fixture:partial-changes"
        return Response(json.dumps(result).encode())
    with tempfile.TemporaryDirectory() as directory:
        token = Path(directory) / "fixture-token"
        token.write_text("fixture-not-a-credential", encoding="utf-8")
        with patch.dict(os.environ, {"LAOMEDO_RUNNER_TOKEN_FILE": str(token)}), \
                patch("urllib.request.urlopen", side_effect=respond):
            results = await Graph.from_payload(flow).arun(inputs=[{}], outputs=["success", "failure", "rejection"])
    return results, calls


def records(results):
    found = []
    def walk(value):
        if hasattr(value, "model_dump"):
            value = value.model_dump()
        if isinstance(value, dict):
            if "destination" in value and "issue_snapshot" in value:
                found.append(value)
                return
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
    walk(results)
    unique = {}
    for record in found:
        unique[json.dumps(record, sort_keys=True)] = record
    return list(unique.values())


class ImportedDemoTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_success_routes_only_simulated_publication(self):
        results, calls = await run_case({"task_outcome": "success", "report": "fixture complete"})
        output = records(results)
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["destination"], "success")
        self.assertEqual(output[0]["publication"]["mode"], "simulated")
        self.assertEqual(output[0]["issue_snapshot"]["context"]["issue"]["node_id"], "FIXTURE_ISSUE_1")
        self.assertEqual(len(calls), 1)
        self.assertIn("FIXTURE_ISSUE_1", calls[0]["payload"]["task"])
        self.assertEqual(calls[0]["payload"]["skill_ref"]["skill_id"], "demo-report")

    async def test_task_failure_is_accepted_and_not_published(self):
        results, _ = await run_case({"task_outcome": "failure", "report": "cannot finish fixture"})
        output = records(results)
        self.assertEqual([item["destination"] for item in output], ["failure"])
        self.assertEqual(output[0]["routed"]["validation"]["contract_status"], "accepted")
        self.assertIsNone(output[0]["publication"])

    async def test_invalid_submission_routes_rejection(self):
        results, _ = await run_case({"task_outcome": "success"})
        output = records(results)
        self.assertEqual([item["destination"] for item in output], ["rejection"])
        self.assertTrue(output[0]["routed"]["validation"]["errors"])
        self.assertIsNone(output[0]["publication"])

    async def test_runtime_interruption_retains_reference_without_publication(self):
        results, _ = await run_case({"task_outcome": "unknown"}, status="interrupted")
        output = records(results)
        self.assertEqual([item["destination"] for item in output], ["rejection"])
        envelope = output[0]["routed"]["validation"]["agent_submission"]
        self.assertEqual(envelope["run_reference"]["run_id"], RUN)
        self.assertEqual(envelope["run_reference"]["trace_ref"], f"laomedo:run:{RUN}:events")
        self.assertFalse(envelope["evidence_complete"])
        self.assertIsNone(output[0]["publication"])

    async def test_fixture_in_request_precheck_correction(self):
        results, calls = await run_case({"task_outcome": "success"}, correction="within_request")
        self.assertEqual([item["contract_status"] for item in calls[0]["fixture_prechecks"]], ["rejected", "accepted"])
        self.assertEqual(calls[0]["fixture_continuations"], 0)
        self.assertEqual([item["destination"] for item in records(results)], ["success"])

    async def test_fixture_exhausted_correction_routes_rejection(self):
        results, calls = await run_case({"task_outcome": "success"}, correction="exhausted")
        self.assertEqual([item["contract_status"] for item in calls[0]["fixture_prechecks"]], ["rejected", "rejected"])
        self.assertEqual(calls[0]["fixture_continuations"], 1)
        self.assertEqual([item["destination"] for item in records(results)], ["rejection"])

    async def test_changed_requirements_pin_cannot_publish(self):
        results, _ = await run_case({"task_outcome": "success", "report": "valid bytes"},
                                   revision_override="sha256:" + "f" * 64)
        output = records(results)
        self.assertEqual([item["destination"] for item in output], ["rejection"])
        self.assertIsNone(output[0]["publication"])

    async def test_incomplete_evidence_cannot_publish_valid_success_form(self):
        results, _ = await run_case({"task_outcome": "success", "report": "valid bytes"},
                                   evidence_complete=False)
        output = records(results)
        self.assertNotEqual(output[0]["destination"], "success")
        self.assertIsNone(output[0]["publication"])

    def test_export_matches_current_component_code_and_frozen_fixture(self):
        exported = json.loads((HERE / "flow.json").read_text(encoding="utf-8"))
        self.assertEqual(exported, builder.build())


if __name__ == "__main__":
    unittest.main()

