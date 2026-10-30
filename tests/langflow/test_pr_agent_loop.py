"""Exercise the native graph with internal fake-provider controls, including negative controls."""

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from lfx.graph.graph.base import Graph
from lfx.schema import Message
from lfx.custom.custom_component.component import Component
from laomedo.github.pull_requests.gateway import GitHubPRGateway
from laomedo.host.mediation.store import MediationStore
from laomedo.github.transport.rest.transport import GitHubRestTransport
from laomedo.integrations.langflow.feedback.pr import operation_value
import test_live_github_pr as fixtures

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "pr_loop_builder", ROOT / "examples/github-pr/build_flow.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class PRAgentLoopTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(
            os.environ,
            {
                "LANGFLOW_CONFIG_DIR": self.temp.name,
                "LANGFLOW_DATABASE_URL": "sqlite:///"
                + (Path(self.temp.name) / "lf.db").as_posix(),
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.fake = fixtures.FakeGitHub()
        self.store = MediationStore(Path(self.temp.name) / "mediation.db")
        _, token = self.store.issue(
            run_id="fixture-run",
            invocation_id="fixture-invoke",
            repository="owner/repo",
            operations={"pr_node_update"},
            branch="demo",
            target_prs={1: "main"},
            ttl_seconds=60,
        )
        self.gateway = GitHubPRGateway(
            {
                "owner/repo": GitHubRestTransport(
                    "owner/repo", lambda: "DUMMY", opener=self.fake
                )
            },
            self.store,
            lambda ref: (
                {"token": token, "run_id": "fixture-run", "repository": "owner/repo"}
                if ref == "fixture-grant"
                else None
            ),
            feedback_grants={"owner/repo#1": "fixture-grant"},
        )
        self.operations = 0
        self.agent_calls = []
        original_update = Component.update_ctx

        def observe(component, values):
            if (
                type(component).__name__ == "PRFixtureAgent"
                and "pr_fixture_agent_calls" in values
            ):
                self.agent_calls.append(values["pr_fixture_agent_task"])
            return original_update(component, values)

        observer = patch.object(Component, "update_ctx", new=observe)
        observer.start()
        self.addCleanup(observer.stop)
        self.before_apply = None

        def request(action, **body):
            if body.get("operation"):
                self.operations += 1
                if self.before_apply:
                    self.before_apply()
            return getattr(self.gateway, action.replace("-", "_"))(**body)

        self.client = patch(
            "laomedo.github.pull_requests.client.pr_request", side_effect=request
        )
        self.client.start()
        self.addCleanup(self.client.stop)

    async def execute(self, action="modify", flow=None):
        graph = Graph.from_payload(flow or builder.build(action))
        result = await asyncio.wait_for(
            graph.arun(inputs=[{}], outputs=["pr"]), timeout=25
        )
        self.last_graph = graph
        return str(result)

    async def test_modify_uses_exact_return_port_and_agent_runs_once(self):
        result = await self.execute()
        self.assertIn("succeeded", result)
        self.assertEqual(len(self.agent_calls), 1)
        self.assertIn("https://github.com/owner/repo/pull/1", self.agent_calls[0])
        self.assertEqual(len(self.fake.writes), 1)
        self.assertEqual(self.fake.prs[1]["title"], "PR operation verified")
        self.assertEqual(len(self.last_graph.vertices), 2)

    async def test_normal_upstream_operation_remains_acyclic(self):
        flow = builder.build()
        pr = flow["data"]["nodes"][0]
        operation = builder.builder.node(
            ROOT / "examples/github-pr/operation.py", "operation", {}, 600, 0
        )
        flow["data"]["nodes"] = [operation, pr]
        flow["data"]["edges"] = [
            builder.builder.helper.edge(operation, "operation", pr, "operation")
        ]
        self.assertIn("succeeded", await self.execute(flow=flow))
        self.assertEqual(len(self.fake.writes), 1)
        self.assertEqual(len(self.agent_calls), 0)

    async def test_external_agent_input_is_refused_before_agent(self):
        flow = builder.build()
        extra = builder.builder.node(
            ROOT / "components/laomedo/github_pr.py", "extra", {}, 900, 0
        )
        flow["data"]["nodes"].append(extra)
        flow["data"]["edges"].append(
            builder.builder.helper.edge(extra, "task", flow["data"]["nodes"][1], "task")
        )
        with self.assertRaisesRegex(Exception, "pr_agent_loop_invalid"):
            await self.execute(flow=flow)
        self.assertEqual(len(self.agent_calls), 0)
        self.assertEqual(len(self.fake.writes), 0)

    async def test_legacy_infinity_feedback_still_runs_once(self):
        flow = builder.build()
        feedback = flow["data"]["edges"][1]
        target = {
            "dataType": "LaomedoGitHubPR",
            "id": "pr",
            "name": "task",
            "output_types": ["Message", "Data"],
        }
        feedback["targetHandle"] = json.dumps(target)
        feedback["data"]["targetHandle"] = target
        self.assertIn("succeeded", await self.execute(flow=flow))
        self.assertEqual(len(self.agent_calls), 1)
        self.assertEqual(len(self.fake.writes), 1)

    async def test_multiple_operation_sources_are_refused_before_agent(self):
        flow = builder.build()
        extra = builder.builder.node(
            ROOT / "examples/github-pr/operation.py", "extra", {}, 900, 0
        )
        flow["data"]["nodes"].append(extra)
        flow["data"]["edges"].append(
            builder.builder.helper.edge(
                extra, "operation", flow["data"]["nodes"][0], "operation"
            )
        )
        with self.assertRaisesRegex(Exception, "pr_agent_loop_invalid"):
            await self.execute(flow=flow)
        self.assertEqual(len(self.agent_calls), 0)
        self.assertEqual(len(self.fake.writes), 0)

    async def test_close_applies_once_and_stops(self):
        self.assertIn("succeeded", await self.execute("close"))
        self.assertEqual(self.fake.prs[1]["state"], "closed")
        self.assertEqual(len(self.agent_calls), 1)

    async def test_new_graph_invocation_reserves_fresh_host_identity(self):
        await self.execute()
        self.assertIn("succeeded", await self.execute())
        self.assertEqual(len(self.fake.writes), 2)
        self.assertEqual(len(self.agent_calls), 2)

    async def test_failed_initial_read_does_not_run_agent(self):
        flow = builder.build()
        flow["data"]["nodes"][0]["data"]["node"]["template"]["pr_choice"]["value"] = ""
        self.assertIn("selected_pr_required", await self.execute(flow=flow))
        self.assertEqual(len(self.agent_calls), 0)
        self.assertEqual(self.operations, 0)

    async def test_invalid_agent_response_cannot_write(self):
        self.assertIn("pr_operation_invalid", await self.execute("invalid"))
        self.assertEqual(self.operations, 0)
        self.assertEqual(len(self.fake.writes), 0)

    async def test_agent_failure_cannot_write_or_retry(self):
        self.assertIn("pr_agent_failed", await self.execute("fail"))
        self.assertEqual(len(self.agent_calls), 1)
        self.assertEqual(self.operations, 0)

    async def test_changed_pr_during_agent_is_refused(self):
        self.before_apply = lambda: self.fake.prs[1].update(body="Concurrent user edit")
        self.assertIn("pr_changed_since_agent_read", await self.execute())
        self.assertEqual(self.fake.prs[1]["body"], "Concurrent user edit")
        self.assertEqual(len(self.fake.writes), 0)

    async def test_unknown_write_stops_without_agent_or_write_retry(self):
        self.fake.timeout_after_write = True
        self.assertIn("unknown", await self.execute())
        self.assertEqual(len(self.agent_calls), 1)
        self.assertEqual(len(self.fake.writes), 1)
        self.assertEqual(self.operations, 1)

    async def test_inline_operation_and_loop_are_refused_without_effect(self):
        flow = builder.build()
        flow["data"]["nodes"][0]["data"]["node"]["template"]["operation"]["value"] = {
            "action": "close",
            "request_id": "inline",
            "grant_ref": "fixture-grant",
        }
        self.assertIn("pr_agent_loop_invalid", await self.execute(flow=flow))
        self.assertEqual(self.operations, 0)
        self.assertEqual(len(self.fake.writes), 0)

    async def test_cancelled_agent_cannot_dispatch_a_write(self):
        started = asyncio.Event()

        async def pending_agent(component, seed):
            started.set()
            await asyncio.Future()

        with patch(
            "laomedo.integrations.langflow.feedback.pr.agent_operation",
            new=pending_agent,
        ):
            run = asyncio.create_task(self.execute())
            await asyncio.wait_for(started.wait(), timeout=10)
            run.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await run
        self.assertEqual(self.operations, 0)
        self.assertEqual(len(self.fake.writes), 0)

    async def test_editor_full_flow_starts_pr_even_when_agent_is_first_in_saved_nodes(
        self,
    ):
        flow = builder.build()
        flow["data"]["nodes"].reverse()
        graph = Graph.from_payload(flow)
        graph.prepare()
        self.assertEqual(graph.first_layer, ["pr"])
        self.assertEqual(graph.sort_vertices(start_component_id="agent"), ["pr"])
        await asyncio.wait_for(graph.arun(inputs=[{}]), timeout=25)
        self.assertEqual(len(self.agent_calls), 1)
        self.assertEqual(len(self.fake.writes), 1)

    async def test_feedback_with_downstream_result_starts_pr_and_runs_agent_once(self):
        flow = builder.build()
        inspector = builder.builder.node(
            ROOT / "examples/github-pr/result.py", "result", {}, 1100, 0
        )
        flow["data"]["nodes"].append(inspector)
        flow["data"]["edges"].append(
            builder.builder.helper.edge(
                flow["data"]["nodes"][0], "operation_result", inspector, "result"
            )
        )
        flow["data"]["nodes"].reverse()
        graph = Graph.from_payload(flow)
        graph.prepare()
        self.assertEqual(graph.first_layer, ["pr"])
        result = await asyncio.wait_for(
            graph.arun(inputs=[{}], outputs=["result"]), timeout=25
        )
        self.assertIn("succeeded", str(result))
        self.assertEqual(len(self.agent_calls), 1)
        self.assertEqual(len(self.fake.writes), 1)

    def test_message_feedback_json_is_supported_but_invalid_or_oversized_refused(self):
        operation = {
            "action": "close",
            "request_id": "once",
            "grant_ref": "fixture-grant",
        }
        self.assertEqual(
            operation_value(Message(text=json.dumps(operation))), operation
        )
        for value in ("not-json", "x" * (1024 * 1024 + 1), {"action": "merge"}, None):
            with self.assertRaisesRegex(ValueError, "pr_operation_invalid"):
                operation_value(value)


class ExportedPRFlowTests(unittest.TestCase):
    def test_saved_internal_export_uses_operation_feedback(self):
        flow = json.loads((ROOT / "examples/github-pr/flow.json").read_text())
        Graph.from_payload(flow)
        edges = flow["data"]["edges"]
        feedback = next(edge for edge in edges if edge["target"] == "pr")
        self.assertEqual(json.loads(feedback["targetHandle"])["fieldName"], "operation")
        self.assertEqual(flow, builder.build())
