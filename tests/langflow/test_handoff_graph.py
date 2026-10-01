"""Pinned runtime graph acceptance, all HTTP responses synthetic."""
import importlib.util
import io
import json
from pathlib import Path
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
    async def test_chain_passes_selected_answer_once(self):
        payloads = []
        def respond(req, **kwargs):
            payloads.append(json.loads(req.data))
            return Response(json.dumps({"run_id": str(len(payloads)), "status": "completed",
                "answer": "SELECTED" if len(payloads) == 1 else "DONE"}).encode())
        with patch("urllib.request.urlopen", side_effect=respond):
            await Graph.from_payload(builder.build()).arun(inputs=[{"input_value": "FIRST"}], types=["chat"])
        self.assertEqual(len(payloads), 2)
        self.assertEqual(payloads[1]["task"], "SELECTED")
        self.assertNotIn("thread_id", payloads[1])

    async def test_failed_first_does_not_dispatch_second(self):
        def respond(*args, **kwargs):
            return Response(json.dumps({"run_id": "one", "status": "failed", "error_category": "fixture"}).encode())
        with patch("urllib.request.urlopen", side_effect=respond) as http:
            with self.assertRaises(Exception):
                await Graph.from_payload(builder.build()).arun(inputs=[{"input_value": "FIRST"}], types=["chat"])
        self.assertEqual(http.call_count, 1)


if __name__ == "__main__":
    unittest.main()
