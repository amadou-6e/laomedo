"""Credential-free native controller tests in pinned Langflow."""
import asyncio
import importlib.util
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from lfx.graph.graph.base import Graph

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
handoff_http = importlib.import_module("laomedo.handoff_http")
spec = importlib.util.spec_from_file_location("controller_component", ROOT / "components/laomedo/bounded_controller.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
build_spec = importlib.util.spec_from_file_location("chain_builder", ROOT / "examples/agent-handoffs/build_flow.py")
builder = importlib.util.module_from_spec(build_spec)
build_spec.loader.exec_module(builder)


class Adapter:
    answers = []
    calls = []
    delay = 0
    def __init__(self, *_):
        pass
    def dispatch(self, envelope, **kwargs):
        if self.delay:
            __import__("time").sleep(self.delay)
        self.calls.append(envelope)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return {"status": "completed", "run_id": "run", "provider": "codex", "answer": answer}
    def cancel(self, *_):
        return {"cancel_acknowledged": False, "reason": "synthetic"}
    def select_artifacts(self, *_):
        return []


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    def flow(self, state, **fields):
        return builder.build_controller(state_directory=state, **fields)

    async def test_graph_loop_success_limits_repetition_and_failure(self):
        cases = [(["next", "DONE"], {}, "success", 2),
                 (["next"], {"max_iterations": 1}, "iteration_limit", 1),
                 (["next"], {"turn_budget": 1}, "turn_budget", 1),
                 (["same", "same"], {}, "no_progress", 2),
                 ([TimeoutError()], {}, "dispatch_uncertain", 1),
                 (["late"], {"deadline_seconds": 1}, "deadline", 1)]
        for answers, fields, expected, count in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as state:
                Adapter.answers, Adapter.calls = answers, []
                Adapter.delay = 1.05 if expected == "deadline" else 0
                with patch.object(handoff_http, "RunnerAdapter", Adapter):
                    await Graph.from_payload(self.flow(state, **fields)).arun(inputs=[{"input_value": "start"}], types=["chat"])
                record = json.loads(next(Path(state).glob("*.json")).read_text())
                self.assertEqual(record["stop_reason"], expected)
                self.assertEqual(len(Adapter.calls), count)

    async def test_cancellation_propagates_and_persists_partial_evidence(self):
        import threading
        entered, release = threading.Event(), threading.Event()
        class Blocking(Adapter):
            def dispatch(self, outgoing, **kwargs):
                entered.set()
                release.wait(3)
                return {"status": "completed", "answer": "late", "run_id": "run"}
            def cancel(self, *_):
                release.set()
                return {"cancel_acknowledged": False, "reason": "synthetic"}
        with tempfile.TemporaryDirectory() as state:
            node = module.LaomedoBoundedController()
            for name, value in {"task": "start", "skills": [{"skill_id": "sample", "revision_id": "sha256:" + "a" * 64}],
                "targets_json": '[{"provider":"codex","model":"m","effort":"low"}]',
                "endpoints_json": '{"codex":"http://localhost:8765"}', "mode": "loop", "stop_answer": "DONE",
                "max_iterations": 2, "turn_budget": 2, "deadline_seconds": 10, "state_directory": state}.items():
                setattr(node, name, value)
            node._pre_run_setup()
            with patch.object(handoff_http, "RunnerAdapter", Blocking):
                task = asyncio.create_task(node.execution_output())
                await asyncio.to_thread(entered.wait, 2)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                await node._dispatch_task
            record = json.loads(next(Path(state).glob("*.json")).read_text())
            self.assertEqual(record["stop_reason"], "cancelled")
            self.assertEqual(record["submitted_turns"], 1)
            self.assertFalse(record["cancel_evidence"]["cancel_acknowledged"])


if __name__ == "__main__":
    unittest.main()
