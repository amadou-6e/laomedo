"""Run inside the pinned Langflow image; all runner traffic is synthetic."""

import asyncio
import importlib.util
import io
import json
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib import error

MODULE_PATH = Path(__file__).resolve().parents[2] / "components/laomedo/codex_agent.py"
spec = importlib.util.spec_from_file_location("codex_agent", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
skill_spec = importlib.util.spec_from_file_location("skill_component", MODULE_PATH.with_name("skill.py"))
skill_module = importlib.util.module_from_spec(skill_spec)
sys.modules[skill_spec.name] = skill_module
skill_spec.loader.exec_module(skill_module)


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


RUN = "aeb54b12-3ca7-43a7-97b3-762dadc94721"
HASH = "sha256:" + "a" * 64


def component(**values):
    node = module.LaomedoCodexAgent()
    for key, value in {"task": "Read fixture", "operation": "fresh", "skill_id": "fixture",
                       "revision_id": HASH, "model": "gpt-6-luna", "effort": "low",
                       "runner_url": "http://host.docker.internal:8765",
                       "timeout_seconds": 210, "run_reference": None, **values}.items():
        setattr(node, key, value)
    node._pre_run_setup()
    return node


def result(**changes):
    return {"run_id": RUN, "status": "completed", "answer": "amber 3",
            "thread_id": "native-thread", "post_run_hash": HASH,
            "requested_model": "gpt-6-luna", "requested_effort": "low",
            "skill": {"revision_id": HASH, "use_evidence": "offered"},
            "raw_event_ref": f"laomedo:run:{RUN}:events", **changes}


class CodexComponentTests(unittest.IsolatedAsyncioTestCase):
    async def test_skill_node_validates_and_agent_consumes_reference(self):
        skill = skill_module.LaomedoSkill()
        skill.skill_id, skill.revision_id = "fixture", HASH
        ref = skill.skill_output()
        node = component(skill_id="", revision_id="", skill_reference=ref)
        _url, payload, _method = node._prepare()
        self.assertEqual(payload["skill_ref"], ref.data)
        with self.assertRaisesRegex(ValueError, "conflicting_skill_inputs"):
            component(skill_reference=ref, revision_id="sha256:" + "b" * 64)._prepare()
        for skill_id, revision in [("../escape", HASH), ("fixture", "latest")]:
            skill.skill_id, skill.revision_id = skill_id, revision
            with self.assertRaises(ValueError):
                skill.skill_output()
    async def test_saved_graph_both_branches_dispatch_once(self):
        from lfx.graph.graph.base import Graph
        root = Path(__file__).resolve().parents[2]
        flow = json.loads((root / "examples/native-codex-node/flow.json").read_text())
        graph = Graph.from_payload(flow)
        with patch.object(module.request, "urlopen", side_effect=lambda *_args, **_kwargs:
                          Response(json.dumps(result()).encode())) as http:
            output = await graph.arun(inputs=[{"input_value": "Read fixture"}],
                                     types=["chat"], outputs=["ChatOutput-laomedo",
                                                           "ChatOutput-run-reference"])
            self.assertEqual(http.call_count, 1)
            self.assertIn("amber 3", str(output))

    async def test_saved_graph_resume_passes_structured_reference(self):
        from lfx.graph.graph.base import Graph
        root = Path(__file__).resolve().parents[2]
        flow = json.loads((root / "examples/native-codex-node/flow.json").read_text())
        node = next(n for n in flow["data"]["nodes"] if n["data"]["type"] == "LaomedoCodexAgent")
        fields = node["data"]["node"]["template"]
        fields["operation"]["value"] = "resume"
        fields["run_reference_json"]["value"] = json.dumps({"run_id": RUN,
            "thread_id": "native-thread", "status": "completed", "post_run_hash": HASH,
            "model": "gpt-6-luna", "effort": "low"})
        def respond(req, timeout):
            self.assertTrue(req.full_url.endswith(f"/{RUN}/resume"))
            self.assertEqual(json.loads(req.data)["expected_post_run_hash"], HASH)
            return Response(json.dumps(result()).encode())
        with patch.object(module.request, "urlopen", side_effect=respond) as http:
            await Graph.from_payload(flow).arun(inputs=[{"input_value": "Read marker"}],
                                                types=["chat"])
            self.assertEqual(http.call_count, 1)

    async def test_both_outputs_submit_once_and_new_build_submits_again(self):
        node = component()
        def respond(req, timeout):
            self.assertEqual(json.loads(req.data)["skill_ref"]["tree_hash"], HASH)
            return Response(json.dumps(result()).encode())
        with patch.object(module.request, "urlopen", side_effect=respond) as http:
            message, data = await asyncio.gather(node.answer_output(), node.run_output())
            self.assertEqual(message.text, "amber 3")
            self.assertEqual(data.data["run_id"], RUN)
            self.assertEqual(data.data["usage"], "unknown")
            self.assertEqual(http.call_count, 1)
            node._pre_run_setup()
            await node.run_output()
            self.assertEqual(http.call_count, 2)

    async def test_invalid_inputs_never_dispatch(self):
        cases = [{"revision_id": "latest"}, {"task": " "},
                 {"runner_url": "https://example.com"}, {"timeout_seconds": 0},
                 {"operation": "resume"}, {"operation": "status", "run_reference": {"run_id": "../x"}}]
        with patch.object(module.request, "urlopen") as http:
            for values in cases:
                with self.subTest(values=values), self.assertRaises(ValueError):
                    await component(**values).run_output()
            http.assert_not_called()

    async def test_resume_exact_binding_and_mismatch(self):
        prior = {"run_id": RUN, "status": "completed", "thread_id": "native-thread",
                 "post_run_hash": HASH, "model": "gpt-6-luna", "effort": "low"}
        def respond(req, timeout):
            self.assertTrue(req.full_url.endswith(f"/{RUN}/resume"))
            payload = json.loads(req.data)
            self.assertEqual(payload["expected_thread_id"], prior["thread_id"])
            self.assertEqual(payload["expected_post_run_hash"], HASH)
            return Response(json.dumps(result()).encode())
        with patch.object(module.request, "urlopen", side_effect=respond) as http:
            await component(operation="resume", run_reference=module.Data(data=prior)).run_output()
            with self.assertRaisesRegex(ValueError, "resume_model_effort_mismatch"):
                await component(operation="resume", run_reference=prior, effort="high").run_output()
            self.assertEqual(http.call_count, 1)

    async def test_failed_run_preserves_identity_and_category(self):
        payload = json.dumps(result(status="timeout", error_category="turn_timeout")).encode()
        with patch.object(module.request, "urlopen", side_effect=error.HTTPError(
                "http://localhost", 502, "failure", {}, Response(payload))):
            with self.assertRaisesRegex(RuntimeError, RUN + " failed: turn_timeout"):
                await component().answer_output()

    async def test_malformed_response_and_transport_failure(self):
        for response, expected in [(Response(b"[]"), "runner_invalid_response"),
                                   (Response(b"not json"), "runner_invalid_response"),
                                   (TimeoutError(), "remote execution may still be active")]:
            with patch.object(module.request, "urlopen", side_effect=(response if
                    isinstance(response, Exception) else None), return_value=response):
                with self.assertRaisesRegex(RuntimeError, expected):
                    await component().run_output()

    async def test_status_and_cancel_use_existing_identity_without_start(self):
        for operation in ["status", "cancel"]:
            node = component(operation=operation, run_reference={"run_id": RUN}, task="")
            def respond(req, timeout):
                self.assertIn("/" + RUN, req.full_url)
                self.assertEqual(req.get_method(), "GET" if operation == "status" else "POST")
                return Response(json.dumps(result(status="running",
                    cancel_requested=operation == "cancel", answer=None)).encode())
            with patch.object(module.request, "urlopen", side_effect=respond):
                data = (await node.run_output()).data
                self.assertEqual(data["status"], "running")


if __name__ == "__main__":
    unittest.main()
