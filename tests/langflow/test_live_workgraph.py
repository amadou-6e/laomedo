"""Imported real publisher wiring, with fake native and host HTTP responses."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lfx.graph.graph.base import Graph
from laomedo.issue_context import fetch_context
from experiments.exp139.run_flow import outcomes

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("live_builder", ROOT / "examples/langflow-workgraph-live/build_flow.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
RUN = "aeb54b12-3ca7-43a7-97b3-762dadc94721"


def frozen_context():
    fixture = json.loads((ROOT / "examples/langflow-workgraph-demo/fixtures.json").read_text())
    def request(path):
        return [] if "/timeline?" in path else fixture["issue"]
    context = fetch_context(fixture["repository"], fixture["issue"]["number"],
                            request=request, fetched_at=fixture["fetched_at"])
    canonical = json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return {"source": "host_frozen_github", "context": context,
            "snapshot_id": "sha256:" + hashlib.sha256(canonical).hexdigest()}


class Response(io.BytesIO):
    def __enter__(self):
        return self
    def __exit__(self, *_):
        self.close()


class LiveGraphTests(unittest.IsolatedAsyncioTestCase):
    async def run_graph(self, submission, *, status="completed", complete=True, snapshot=None):
        flow = builder.build(snapshot or frozen_context(), "Bounded fixture task",
                             runner_url="http://127.0.0.1:8765", model="fixture")
        # Export then import; the original builder Graph is never executed.
        flow = json.loads(json.dumps(flow))
        agent_calls, publisher_calls = [], []
        self.agent_calls = agent_calls
        def respond(req, **kwargs):
            payload = json.loads(req.data)
            agent_calls.append(payload)
            return Response(json.dumps({"run_id": RUN, "thread_id": "fixture-thread",
                "status": status, "answer": json.dumps(submission), "attempt_finished": True,
                "client_request_id": payload["request_id"],
                "evidence_complete": complete, "completion_basis": "native_trace_closure",
                "requirements_revision": payload["output_requirements"]["requirements_revision"],
                "raw_event_ref": f"laomedo:run:{RUN}:events",
                "post_run_hash": "sha256:" + "a" * 64}).encode())
        def publish(_opener, req, **kwargs):
            publisher_calls.append({"url": req.full_url, "body": json.loads(req.data)})
            return Response(json.dumps({"run_id": RUN, "publication_handoff": {
                "phase": "completed", "publication": {"state": "confirmed"}}}).encode())
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / "token"
            token.write_text("not-a-credential")
            with patch.dict(os.environ, {"LAOMEDO_RUNNER_TOKEN_FILE": str(token)}), \
                    patch("urllib.request.urlopen", side_effect=respond), \
                    patch("urllib.request.OpenerDirector.open", new=publish):
                result = await Graph.from_payload(flow).arun(inputs=[{}],
                    outputs=["publisher", "failure", "rejection", "recovery"])
        return result, agent_calls, publisher_calls

    async def test_success_routes_to_real_publisher_with_empty_request(self):
        _, agent, publisher = await self.run_graph({"task_outcome": "success", "report": "done"})
        self.assertEqual(len(agent), 1)
        self.assertEqual(publisher, [{"url": f"http://127.0.0.1:8765/v1/runs/{RUN}/publish", "body": {}}])
        self.assertNotIn("github_authorization_ref", agent[0])
        self.assertIn("frozen_issue", agent[0]["task"])
        self.assertEqual(agent[0]["skill_ref"]["skill_id"], "live-report")

    async def test_failure_rejection_and_recovery_never_request_publication(self):
        cases = [({"task_outcome": "failure", "report": "failed"}, "completed", True, "failure"),
                 ({"task_outcome": "success"}, "completed", True, "rejection"),
                 ({"task_outcome": "success", "report": "partial"}, "interrupted", False, "recovery"),
                 ({"task_outcome": "success", "report": "done"}, "completed", "unknown", "recovery")]
        for submission, status, complete, destination in cases:
            with self.subTest(submission=submission, status=status, complete=complete):
                result, agent, publisher = await self.run_graph(submission, status=status, complete=complete)
                self.assertEqual(len(agent), 1)
                self.assertEqual(publisher, [])
                self.assertEqual([value["destination"] for value in outcomes(result)], [destination])

    async def test_changed_frozen_issue_refuses_before_agent_dispatch(self):
        snapshot = frozen_context()
        snapshot["context"]["issue"]["body"] += "changed"
        with self.assertRaisesRegex(Exception, "frozen_issue_context_invalid"):
            await self.run_graph({"task_outcome": "success", "report": "done"}, snapshot=snapshot)
        self.assertEqual(self.agent_calls, [])


if __name__ == "__main__":
    unittest.main()
