"""Pinned runtime graph acceptance, all HTTP responses synthetic."""
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
spec = importlib.util.spec_from_file_location("chain_builder", ROOT / "examples/agent-handoffs/build_flow.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class Response(io.BytesIO):
    def __enter__(self):
        return self
    def __exit__(self, *_):
        self.close()


class GraphTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        token = Path(temporary.name) / "api-token"
        token.write_text("synthetic-token", encoding="utf-8")
        environment = patch.dict(os.environ, {"LAOMEDO_RUNNER_TOKEN_FILE": str(token)})
        environment.start()
        self.addCleanup(environment.stop)

    async def test_chain_passes_selected_answer_once(self):
        payloads = []
        flow = builder.build()
        self.assertEqual(len({edge["id"] for edge in flow["data"]["edges"]}), len(flow["data"]["edges"]))
        def respond(req, **kwargs):
            payloads.append(json.loads(req.data))
            result = {"run_id": str(len(payloads)), "status": "completed",
                "answer": "SELECTED" if len(payloads) == 1 else "DONE"}
            if "request_id" in payloads[-1]:
                result["client_request_id"] = payloads[-1]["request_id"]
            return Response(json.dumps(result).encode())
        with patch("urllib.request.urlopen", side_effect=respond):
            await Graph.from_payload(flow).arun(inputs=[{"input_value": "FIRST"}], types=["chat"])
        self.assertEqual(len(payloads), 2)
        self.assertEqual(payloads[1]["task"], "SELECTED")
        self.assertNotIn("thread_id", payloads[1])
        self.assertIn("handoff", payloads[1])
        self.assertEqual(payloads[1]["handoff"]["source"]["run_id"], "1")

    async def test_failed_first_does_not_dispatch_second(self):
        def respond(req, **kwargs):
            payload = json.loads(req.data)
            result = {"run_id": "one", "status": "failed", "error_category": "fixture"}
            if "request_id" in payload:
                result["client_request_id"] = payload["request_id"]
            return Response(json.dumps(result).encode())
        with patch("urllib.request.urlopen", side_effect=respond) as http:
            with self.assertRaises(Exception):
                await Graph.from_payload(builder.build()).arun(inputs=[{"input_value": "FIRST"}], types=["chat"])
        self.assertEqual(http.call_count, 1)


if __name__ == "__main__":
    unittest.main()
