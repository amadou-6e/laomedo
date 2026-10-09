"""Run inside the pinned Langflow image; all runner traffic is synthetic."""

import asyncio
from copy import deepcopy
import importlib.util
import io
import json
import os
import sys
import threading
from types import SimpleNamespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, PropertyMock
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
    async def test_opt_in_join_uses_saved_flow_identity_and_polls_bridge(self):
        node = component(bridge_url="http://host.docker.internal:8766")
        node._vertex = SimpleNamespace(id="agent-stage")
        native_run = str(__import__("uuid").uuid4())
        calls = []

        def bridge_open(req, timeout):
            calls.append((req.full_url, req.get_method(), req.data))
            if req.full_url.endswith("/v1/invocations"):
                submitted = json.loads(req.data)
                self.assertEqual(submitted["flow_id"], "saved-flow")
                self.assertEqual(submitted["graph_run_id"], "graph-run")
                self.assertEqual(submitted["stage_id"], "agent-stage")
                self.assertEqual(submitted["runner_body"]["task"], "Read fixture")
                value = {"run_id": native_run, "status": "prepared",
                         "client_request_id": submitted["client_request_id"]}
            else:
                value = {**result(run_id=native_run), "client_request_id":
                         json.loads(calls[0][2])["client_request_id"]}
            return Response(json.dumps(value).encode())

        with patch.object(type(node), "graph", new_callable=PropertyMock,
                          return_value=SimpleNamespace(flow_id="saved-flow",
                                                       run_id="graph-run")), \
                patch.object(node, "_token", return_value="synthetic"), \
                patch.object(module._HTTP, "open", side_effect=bridge_open):
            output = (await node.run_output()).data
        self.assertEqual(output["status"], "completed")
        self.assertEqual(output["run_id"], native_run)
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[1][0].endswith("/v1/runs/" + native_run))

    async def test_cancelled_component_resolves_same_request_without_redispatch(self):
        node = component(operation="start", request_id=RUN)
        entered, release = threading.Event(), threading.Event()
        def blocked_http(*_args):
            entered.set()
            release.wait(timeout=3)
            return {"run_id": RUN, "status": "prepared"}
        with patch.object(node, "_http", side_effect=blocked_http) as post, \
                patch.object(node, "_cancel_after_ui_stop") as stop:
            task = asyncio.create_task(node.run_output())
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(.01)
            self.assertTrue(entered.is_set())
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            await node._cancel_task
            release.set()
            await node._dispatch_task
            self.assertEqual(post.call_count, 1)
            self.assertEqual(stop.call_count, 1)
            self.assertEqual(stop.call_args.args[1], RUN)
            self.assertTrue(stop.call_args.args[2].startswith("sha256:"))

    async def test_stop_lookup_cancels_only_matching_nonterminal_run(self):
        node = component(operation="start", request_id=RUN)
        expected_hash = "sha256:" + "c" * 64
        lookup = {"client_request_id": RUN, "request_hash": expected_hash,
                  "run_id": RUN, "status": "prepared"}
        with patch.object(node, "_stop_http", side_effect=[None, lookup,
                {"run_id": RUN, "status": "cancelled", "cancel_requested": True},
                {"run_id": RUN, "status": "cancelled", "cancel_confirmed": True}]) as http:
            node._cancel_after_ui_stop("http://host.docker.internal:8765", RUN, expected_hash)
        self.assertEqual(http.call_count, 4)
        self.assertEqual(http.call_args_list[2].args[0],
                         "http://host.docker.internal:8765/v1/runs/" + RUN + "/cancel")
        self.assertIn("cancellation confirmed", node.status)

    async def test_stop_binding_conflict_and_completed_control_send_no_cancel(self):
        node = component(operation="start", request_id=RUN)
        good = "sha256:" + "c" * 64
        bad = {"client_request_id": RUN, "request_hash": "sha256:" + "d" * 64,
               "run_id": RUN, "status": "running"}
        with patch.object(node, "_stop_http", return_value=bad) as http:
            node._cancel_after_ui_stop("http://host.docker.internal:8765", RUN, good)
        self.assertEqual(http.call_count, 1)
        self.assertIn("binding_conflict", node.status)
        completed = {"client_request_id": RUN, "request_hash": good,
                     "run_id": RUN, "status": "completed"}
        with patch.object(node, "_stop_http", return_value=completed) as http:
            node._cancel_after_ui_stop("http://host.docker.internal:8765", RUN, good)
        self.assertEqual(http.call_count, 1)
        self.assertIn("no cancel sent", node.status)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        token = Path(temporary.name) / "api-token"
        token.write_text("test-runner-token", encoding="utf-8")
        environment = patch.dict(os.environ, {"LAOMEDO_RUNNER_TOKEN_FILE": str(token)})
        environment.start()
        self.addCleanup(environment.stop)

    async def test_multiple_skill_inputs_and_repeated_ids(self):
        refs = [module.Data(data={"skill_id": name, "revision_id": HASH, "tree_hash": HASH})
                for name in ("first", "second")]
        node = component(skill_reference=refs, skill_id="", revision_id="")
        payload = node._prepare()[1]
        self.assertEqual(payload["skill_refs"], [ref.data for ref in refs])
        with self.assertRaisesRegex(ValueError, "duplicate_skill_id"):
            component(skill_reference=[refs[0], refs[0]], skill_id="", revision_id="")._prepare()
        with self.assertRaisesRegex(ValueError, "conflicting_skill_inputs"):
            component(skill_reference=refs)._prepare()

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
        with patch.object(module.request, "urlopen", side_effect=lambda req, **_kwargs:
                          Response(json.dumps(result(client_request_id=
                              json.loads(req.data)["request_id"])).encode())) as http:
            output = await graph.arun(inputs=[{"input_value": "Read fixture"}],
                                     types=["chat"], outputs=["ChatOutput-laomedo",
                                                           "ChatOutput-run-reference"])
            self.assertEqual(http.call_count, 1)
            self.assertIn("amber 3", str(output))

    async def test_pinned_graph_exposes_run_and_stage_ids_without_flow_id(self):
        from lfx.graph.graph.base import Graph
        root = Path(__file__).resolve().parents[2]
        flow = json.loads((root / "examples/native-codex-node/flow.json").read_text())
        agent = next(node for node in flow["data"]["nodes"]
                     if node["data"]["type"] == "LaomedoCodexAgent")
        code = agent["data"]["node"]["template"]["code"]["value"]
        source = '            return endpoint, payload, "POST"'
        probe = ('            payload["langflow_probe"] = {"run_id": self.graph.run_id, '
                 '"flow_id": self.graph.flow_id, "stage_id": self._vertex.id}\n'
                 + source)
        self.assertEqual(code.count(source), 1)
        prefix, separator, suffix = code.rpartition(source)
        self.assertTrue(separator)
        agent["data"]["node"]["template"]["code"]["value"] = prefix + probe + suffix
        observed = []

        def respond(req, **_kwargs):
            payload = json.loads(req.data)
            probe = payload["langflow_probe"]
            observed.append((probe["run_id"], probe["flow_id"], probe["stage_id"]))
            return Response(json.dumps(result(client_request_id=payload["request_id"])).encode())
        with patch.object(module.request, "urlopen", side_effect=respond):
            for _ in range(2):
                await Graph.from_payload(flow).arun(
                    inputs=[{"input_value": "Read fixture"}], types=["chat"])
        self.assertEqual(len(observed), 2)
        self.assertNotEqual(observed[0][0], observed[1][0])
        self.assertEqual(observed[0][1:], observed[1][1:])
        self.assertTrue(observed[0][0])
        self.assertEqual(observed[0][2], "LaomedoCodexAgent-native")
        # Direct Graph.from_payload runs need not have a saved server flow ID.
        self.assertIsNone(observed[0][1])

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

    async def test_two_connected_skill_nodes_dispatch_one_skill_list(self):
        from lfx.graph.graph.base import Graph
        root = Path(__file__).resolve().parents[2]
        flow = json.loads((root / "examples/native-codex-node/flow.json").read_text())
        skill = next(n for n in flow["data"]["nodes"] if n["data"]["type"] == "LaomedoSkill")
        second = deepcopy(skill)
        second["id"] = second["data"]["id"] = "LaomedoSkill-second"
        second["data"]["node"]["template"]["skill_id"]["value"] = "second"
        flow["data"]["nodes"].append(second)
        edge = deepcopy(next(e for e in flow["data"]["edges"] if e["source"] == skill["id"]))
        edge["id"] += "-second"
        edge["source"] = second["id"]
        edge["data"]["sourceHandle"]["id"] = second["id"]
        edge["sourceHandle"] = json.dumps(edge["data"]["sourceHandle"])
        flow["data"]["edges"].append(edge)
        def respond(req, timeout):
            refs = json.loads(req.data)["skill_refs"]
            self.assertEqual({r["skill_id"] for r in refs},
                             {"second", skill["data"]["node"]["template"]["skill_id"]["value"]})
            return Response(json.dumps(result(client_request_id=
                json.loads(req.data)["request_id"])).encode())
        with patch.object(module.request, "urlopen", side_effect=respond) as http:
            await Graph.from_payload(flow).arun(inputs=[{"input_value": "Use both skills"}], types=["chat"])
            self.assertEqual(http.call_count, 1)

    async def test_both_outputs_submit_once_and_new_build_submits_again(self):
        node = component()
        def respond(req, timeout):
            payload = json.loads(req.data)
            self.assertEqual(payload["skill_ref"]["tree_hash"], HASH)
            self.assertEqual(req.get_header("Authorization"), "Bearer test-runner-token")
            return Response(json.dumps(result(client_request_id=payload["request_id"])).encode())
        with patch.object(module.request, "urlopen", side_effect=respond) as http:
            message, data = await asyncio.gather(node.answer_output(), node.run_output())
            self.assertEqual(message.text, "amber 3")
            self.assertEqual(data.data["run_id"], RUN)
            self.assertEqual(data.data["usage"], "unknown")
            self.assertEqual(http.call_count, 1)
            node._pre_run_setup()
            await node.run_output()
            self.assertEqual(http.call_count, 2)

    async def test_nonblocking_start_exposes_early_id_and_stable_retry_key(self):
        node = component(operation="start")
        seen = []
        def respond(req, timeout):
            self.assertTrue(req.full_url.endswith("/v1/runs/async"))
            payload = json.loads(req.data)
            seen.append(payload["request_id"])
            return Response(json.dumps(result(status="prepared", answer=None,
                client_request_id=payload["request_id"])).encode())
        with patch.object(module.request, "urlopen", side_effect=respond) as http:
            early = (await node.run_output()).data
            self.assertEqual(early["status"], "prepared")
            self.assertEqual(early["run_id"], RUN)
            self.assertEqual(early["request_id"], seen[0])
            await node.answer_output()
            self.assertEqual(http.call_count, 1)
            node.request_id = seen[0]
            node._pre_run_setup()
            await node.run_output()
            self.assertEqual(seen[0], seen[1])
        with self.assertRaisesRegex(ValueError, "invalid_request_id"):
            await component(operation="start", request_id="not-a-uuid").run_output()

    async def test_uncertain_start_error_retains_retry_identity(self):
        node = component(operation="start")
        with patch.object(module.request, "urlopen", side_effect=TimeoutError()):
            with self.assertRaisesRegex(RuntimeError, "retry only with request_id") as caught:
                await node.run_output()
        self.assertIn(node._generated_request_id, str(caught.exception))

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

    async def test_repeated_cancel_accepts_terminal_runner_record(self):
        node = component(operation="cancel", run_reference={"run_id": RUN}, task="")
        payload = json.dumps(result(status="cancelled", answer=None)).encode()
        with patch.object(module.request, "urlopen", side_effect=error.HTTPError(
                "http://localhost", 502, "terminal", {}, Response(payload))):
            self.assertEqual((await node.run_output()).data["status"], "cancelled")

    async def test_missing_runner_token_fails_before_request(self):
        with patch.dict(os.environ, {"LAOMEDO_RUNNER_TOKEN_FILE": "missing-token-file"}):
            with patch.object(module.request, "urlopen") as http:
                with self.assertRaisesRegex(RuntimeError, "runner_api_token_file_unavailable"):
                    await component().run_output()
                http.assert_not_called()


if __name__ == "__main__":
    unittest.main()

