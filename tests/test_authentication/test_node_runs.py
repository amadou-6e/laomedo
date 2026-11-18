"""Native graph selection projection, without executing a graph or provider."""

from copy import deepcopy
import unittest
from uuid import uuid4

from laomedo.github.node_runs.errors import GitHubNodeAuthorizationError
from laomedo.github.node_runs.authority import GitHubRunAuthority
from laomedo.integrations.langflow.authentication.catalog import GitHubGraphCatalog
from laomedo.integrations.langflow.authentication.node_runs import (
    GitHubNodeRunAdmission,
)
from test_github.test_node_runs.test_authority import NodeConnectionFixture


class GitHubNodeRunAdmissionTests(unittest.IsolatedAsyncioTestCase):
    """The host derives every saved-account node and cannot approve hidden targets."""

    def setUp(self):
        self.connections = NodeConnectionFixture()
        self.authority = GitHubRunAuthority(self.connections)
        self.catalog = GitHubGraphCatalog.capture(
            {
                "github": {
                    kind: {"template": {"code": {"value": "synthetic catalog source"}}}
                    for kind in ("LaomedoGitHubIssue", "LaomedoGitHubPR")
                }
            }
        )
        self.admission = GitHubNodeRunAdmission(self.authority, self.catalog)
        self.scope = self.connections.scope()
        self.flow = uuid4()
        self.graph = {
            "nodes": [
                {
                    "id": "pr-1",
                    "position": {"x": 1, "y": 2},
                    "data": {
                        "type": "LaomedoGitHubPR",
                        "node": {
                            "template": {
                                "code": {"value": "synthetic catalog source"},
                                "github_connection": {
                                    "value": str(self.connections.connection)
                                },
                                "repository_url": {
                                    "value": "https://github.com/synthetic/private"
                                },
                                "pr_choice": {"value": "#12 Selected PR"},
                            }
                        },
                    },
                }
            ],
            "edges": [],
            "viewport": {"x": 1, "y": 2, "zoom": 1},
        }

    async def test_read_plan_derives_saved_identity_without_operations(self):
        _, nodes = await self.admission.prepare(self.scope, self.flow, self.graph)
        selection = nodes[0].selection
        self.assertEqual(selection.vertex_id, "pr-1")
        self.assertEqual(selection.connection_id, self.connections.connection)
        self.assertEqual(selection.number, 12)
        self.assertEqual(selection.operations, ())

    async def test_posted_name_cannot_hide_a_canonical_github_node(self):
        self.graph["nodes"][0]["data"]["node"]["name"] = "TextOutput"
        _, nodes = await self.admission.prepare(self.scope, self.flow, self.graph)
        self.assertEqual(nodes[0].selection.kind, "pr")

    async def test_modified_source_and_unclassified_disconnected_nodes_never_prepare(
        self,
    ):
        graph = deepcopy(self.graph)
        graph["nodes"][0]["data"]["node"]["template"]["code"]["value"] += "modified"
        with self.assertRaises(GitHubNodeAuthorizationError):
            await self.admission.prepare(self.scope, self.flow, graph)
        graph = deepcopy(self.graph)
        other = deepcopy(graph["nodes"][0])
        other["id"] = "unreachable"
        other["data"]["type"] = "PythonInterpreter"
        graph["nodes"].append(other)
        with self.assertRaises(GitHubNodeAuthorizationError):
            await self.admission.prepare(self.scope, self.flow, graph)
        self.assertEqual(self.authority.pending, {})

    async def test_agent_return_uses_native_data_handle_not_forged_canvas_handle(self):
        self.graph["edges"] = [
            {
                "source": "agent-1",
                "target": "pr-1",
                "targetHandle": '{"fieldName":"unrelated"}',
                "data": {"targetHandle": {"fieldName": "pr_context"}},
            }
        ]
        _, nodes = await self.admission.prepare(self.scope, self.flow, self.graph)
        self.assertEqual(nodes[0].selection.operations, ("modify", "close"))
        self.graph["nodes"][0]["data"]["node"]["template"]["pr_choice"]["value"] = ""
        with self.assertRaises(GitHubNodeAuthorizationError):
            await self.admission.prepare(self.scope, self.flow, self.graph)

    async def test_wrong_connection_and_nonconsented_repository_never_prepare(self):
        for field, value in (
            ("github_connection", str(uuid4())),
            ("repository_url", "https://github.com/other/private"),
        ):
            graph = deepcopy(self.graph)
            graph["nodes"][0]["data"]["node"]["template"][field]["value"] = value
            with self.assertRaises(GitHubNodeAuthorizationError):
                await self.admission.prepare(self.scope, self.flow, graph)
        self.assertEqual(self.authority.pending, {})

    async def test_all_saved_nodes_are_listed_and_host_is_only_an_explicit_option(self):
        other = deepcopy(self.graph["nodes"][0])
        other["id"] = "issue-2"
        other["data"]["type"] = "LaomedoGitHubIssue"
        other["data"]["node"]["template"]["issue_choice"] = {
            "value": "#8 Selected Issue"
        }
        self.graph["nodes"].append(other)
        _, nodes = await self.admission.prepare(self.scope, self.flow, self.graph)
        self.assertEqual(
            {node.selection.vertex_id for node in nodes}, {"pr-1", "issue-2"}
        )
        for node in self.graph["nodes"]:
            node["data"]["node"]["template"]["github_connection"]["value"] = "host"
        self.assertIsNone(
            await self.admission.prepare(self.scope, self.flow, self.graph)
        )
        self.graph["nodes"][0]["data"]["node"]["template"]["github_connection"][
            "value"
        ] = ""
        with self.assertRaises(GitHubNodeAuthorizationError):
            await self.admission.prepare(self.scope, self.flow, self.graph)

    def test_canvas_moves_preserve_digest_but_parameter_and_edge_changes_do_not(self):
        normalized = self.admission.executable_graph(self.graph)
        digest = self.authority.digest_graph(normalized)
        graph = deepcopy(self.graph)
        graph["nodes"][0]["position"] = {"x": 100, "y": 200}
        graph["nodes"][0]["selected"] = True
        graph["viewport"]["zoom"] = 2
        self.assertEqual(
            digest, self.authority.digest_graph(self.admission.executable_graph(graph))
        )
        graph["nodes"][0]["data"]["node"]["template"]["pr_choice"][
            "value"
        ] = "#99 Another PR"
        self.assertNotEqual(
            digest, self.authority.digest_graph(self.admission.executable_graph(graph))
        )
        self.assertIn("position", self.graph["nodes"][0])

    async def test_static_pr_request_is_approved_but_previous_outcome_is_not_replayed(
        self,
    ):
        template = self.graph["nodes"][0]["data"]["node"]["template"]
        template["pr_context"] = {
            "value": {
                "action": "close",
                "request_id": "effect",
                "grant_ref": "reference",
            }
        }
        _, nodes = await self.admission.prepare(self.scope, self.flow, self.graph)
        self.assertEqual(nodes[0].selection.operations, ("close",))
        template["pr_context"] = {
            "value": {
                "pr": {"repository": "synthetic/private", "number": 12},
                "operation": {"status": "succeeded"},
            }
        }
        _, nodes = await self.admission.prepare(self.scope, self.flow, self.graph)
        self.assertEqual(nodes[0].selection.operations, ())

    async def test_static_issue_operation_is_write_capable_and_tool_mode_is_refused(
        self,
    ):
        data = self.graph["nodes"][0]["data"]
        data["type"] = "LaomedoGitHubIssue"
        data["node"]["template"]["issue_choice"] = {"value": "#8 Selected Issue"}
        data["node"]["template"]["operation"] = {
            "value": {"action": "modify", "changes": {"title": "Requested"}}
        }
        _, nodes = await self.admission.prepare(self.scope, self.flow, self.graph)
        self.assertEqual(nodes[0].selection.operations, ("modify",))
        data["node"]["tool_mode"] = True
        with self.assertRaises(GitHubNodeAuthorizationError):
            await self.admission.prepare(self.scope, self.flow, self.graph)
