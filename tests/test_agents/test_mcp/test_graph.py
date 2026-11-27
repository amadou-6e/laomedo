"""Native graph scheduling checks; runner replies are controlled, not live agents."""

from copy import deepcopy
from importlib.util import find_spec
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from laomedo.integrations.langflow.mcp_graph import McpGraphPolicy
from support.paths import repository_root


class McpDependencyTests(unittest.TestCase):
    """Preserve shared branches, unrelated nodes and the caller's saved graph."""

    @staticmethod
    def node(identifier, operation=None):
        return {
            "id": identifier,
            "data": {
                "type": "LaomedoCodexAgent" if operation else "MCPTools",
                "node": {"template": {"operation": {"value": operation}}},
            },
        }

    @staticmethod
    def edge(source, target, field="mcp_tools"):
        return {
            "source": source,
            "target": target,
            "data": {"targetHandle": {"fieldName": field}},
        }

    def test_shared_active_dependency_and_saved_wiring_are_preserved(self):
        nodes = [
            self.node("mcp"),
            self.node("status", "status"),
            self.node("fresh", "fresh"),
        ]
        edges = [self.edge("mcp", "status"), self.edge("mcp", "fresh")]
        original = deepcopy((nodes, edges))
        kept_nodes, kept_edges = McpGraphPolicy.execution_graph(nodes, edges)
        self.assertEqual(kept_nodes, nodes)
        self.assertEqual(kept_edges, [edges[1]])
        self.assertEqual((nodes, edges), original)

    def test_exclusive_ancestors_are_removed_but_unrelated_nodes_remain(self):
        nodes = [self.node(n) for n in ("config", "mcp", "unrelated")] + [
            self.node("cancel", "cancel")
        ]
        edges = [self.edge("config", "mcp", "config"), self.edge("mcp", "cancel")]
        kept_nodes, kept_edges = McpGraphPolicy.execution_graph(nodes, edges)
        self.assertEqual({n["id"] for n in kept_nodes}, {"cancel", "unrelated"})
        self.assertEqual(kept_edges, [])

    def test_explicit_mcp_play_and_cycles_keep_requested_nodes(self):
        nodes = [self.node("mcp"), self.node("status", "status")]
        edges = [self.edge("mcp", "status"), self.edge("status", "mcp", "config")]
        kept, _ = McpGraphPolicy.execution_graph(nodes, edges)
        self.assertIn("status", {n["id"] for n in kept})
        kept, _ = McpGraphPolicy.execution_graph(nodes, edges, {"mcp"})
        self.assertEqual({n["id"] for n in kept}, {"status", "mcp"})


@unittest.skipUnless(find_spec("lfx"), "Requires optional native Langflow runtime")
class NativeMcpControlGraphTests(unittest.IsolatedAsyncioTestCase):
    """Exercise native scheduling and input resolution with an unavailable MCP output."""

    async def asyncSetUp(self):
        from lfx.graph.graph.base import Graph
        from lfx.services.manager import get_service_manager
        from lfx.services.schema import ServiceType
        from lfx.services.settings.service import SettingsService
        from lfx.services.settings.base import Settings
        from lfx.services.settings.auth import AuthSettings

        directory = self.enterContext(tempfile.TemporaryDirectory())
        service = SettingsService(
            Settings(config_dir=directory), AuthSettings(CONFIG_DIR=directory)
        )
        self.enterContext(
            patch.dict(
                get_service_manager().services, {ServiceType.SETTINGS_SERVICE: service}
            )
        )
        self.enterContext(patch.object(Graph, "initialize", Graph.initialize))
        self.enterContext(patch.object(Graph, "sort_vertices", Graph.sort_vertices))
        McpGraphPolicy.install()

    def flow(self, operation):
        from lfx.components.models_and_agents.mcp_component import MCPToolsComponent

        flow = json.loads(
            (
                repository_root() / "tests/test_agents/test_examples/data/codex.json"
            ).read_text(encoding="utf-8")
        )["data"]
        agent = next(
            n for n in flow["nodes"] if n["data"]["type"] == "LaomedoCodexAgent"
        )
        self.run_id = str(uuid4())
        fields = agent["data"]["node"]["template"]
        fields["operation"]["value"] = operation
        fields["run_reference_json"]["value"] = json.dumps(
            {"provider": "codex", "run_id": self.run_id}
        )
        component = MCPToolsComponent()
        native = component.to_frontend_node()["data"]["node"]
        native["tool_mode"] = True
        output = component._build_tool_output().model_dump(mode="json")
        native["outputs"] = [output]
        mcp = {
            "id": "unavailable-mcp",
            "data": {"id": "unavailable-mcp", "type": "MCPTools", "node": native},
        }
        source = {
            "id": mcp["id"],
            "dataType": "MCPTools",
            "name": output["name"],
            "output_types": ["Tool"],
        }
        target = {
            "id": agent["id"],
            "fieldName": "mcp_tools",
            "inputTypes": ["Tool"],
            "type": "other",
        }
        edge = {
            "id": "mcp-agent",
            "source": mcp["id"],
            "target": agent["id"],
            "sourceHandle": json.dumps(source),
            "targetHandle": json.dumps(target),
            "data": {"sourceHandle": source, "targetHandle": target},
        }
        return {"nodes": [mcp, agent], "edges": [edge]}

    async def test_status_and_cancel_reach_runner_without_building_mcp(self):
        from lfx.graph.graph.base import Graph
        from lfx.custom.custom_component.component import Component
        from laomedo.agents.interface.langflow.component import AgentComponent

        for operation, method in (("status", "GET"), ("cancel", "POST")):
            with self.subTest(operation=operation):
                flow = self.flow(operation)
                saved = deepcopy(flow)
                attempts = []
                original_output = Component._get_output_result

                async def unavailable(component, output):
                    if output.method == "to_toolkit":
                        attempts.append(component)
                        raise ConnectionError("MCP server is down")
                    return await original_output(component, output)

                with (
                    patch.object(Component, "_get_output_result", unavailable),
                    patch.object(
                        AgentComponent,
                        "_http",
                        return_value={
                            "run_id": self.run_id,
                            "status": (
                                "cancelled" if operation == "cancel" else "completed"
                            ),
                        },
                    ) as runner,
                ):
                    await Graph.from_payload(flow).arun(
                        inputs=[{"input_value": ""}], types=["chat"]
                    )
                self.assertEqual(attempts, [])
                self.assertEqual(runner.call_args.args[2], method)
                self.assertEqual(flow, saved)
                # Falsifier: without filtering, this very graph builds the failed
                # Toolset before it can contact the runner.
                with (
                    patch.object(Component, "_get_output_result", unavailable),
                    patch.object(
                        McpGraphPolicy,
                        "execution_graph",
                        side_effect=lambda n, e, _: (n, e),
                    ),
                    patch.object(AgentComponent, "_http") as blocked_runner,
                ):
                    with self.assertRaisesRegex(Exception, "MCP server is down"):
                        await Graph.from_payload(flow).arun(
                            inputs=[{"input_value": ""}], types=["chat"]
                        )
                self.assertTrue(attempts)
                blocked_runner.assert_not_called()

    async def test_effective_operation_and_rebuild_restore_dependencies(self):
        from lfx.graph.graph.base import Graph

        flow = self.flow("status")
        graph = Graph.from_payload(flow)
        agent = next(v for v in graph.vertices if v.data["type"] == "LaomedoCodexAgent")
        agent.update_raw_params({"operation": "fresh"})
        graph.sort_vertices()
        self.assertIn("unavailable-mcp", graph.vertices_to_run)
        agent.update_raw_params({"operation": "cancel"})
        graph.sort_vertices()
        self.assertNotIn("unavailable-mcp", graph.vertices_to_run)
        self.assertEqual(agent.params["mcp_tools"], [])
        agent.update_raw_params({"operation": "fresh"})
        graph.sort_vertices()
        self.assertIn("unavailable-mcp", graph.vertices_to_run)
        clone = graph.copy_for_run(user_id=None)
        self.assertIn("unavailable-mcp", clone.vertex_map)
        self.assertEqual(len(clone.edges), 1)
        graph.initialize()
        self.assertIn("unavailable-mcp", graph.vertex_map)
        graph.sort_vertices(start_component_id="unavailable-mcp")
        self.assertIn("unavailable-mcp", graph.vertices_to_run)
