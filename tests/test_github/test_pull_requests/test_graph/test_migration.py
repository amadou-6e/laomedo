"""Explicit saved-graph migration controls; never executes the graph."""

import unittest
from importlib.util import find_spec

if find_spec("lfx") is None:
    raise unittest.SkipTest("Optional lfx runtime is not installed")

import copy
import json
from laomedo.integrations.langflow.pr_context.migration import migrate_pr_graph
from test_github.test_pull_requests.test_graph import builder


class PRMigrationTests(unittest.TestCase):
    def setUp(self):
        self.pr = builder.node(
            builder.ROOT / "components/laomedo/github_pr.py",
            "pr",
            {
                "repository_url": "https://github.com/owner/repo",
                "pr_choice": "#1 Saved",
                "state": "closed",
                "labels": ["backend"],
            },
            10,
            20,
        )
        self.definition = copy.deepcopy(self.pr["data"]["node"])
        old = self.pr["data"]["node"]
        old["template"].pop("pr_context")
        old["template"]["pr_reference"] = {
            "type": "other",
            "input_types": ["Data"],
            "value": None,
        }
        old["template"]["operation"] = {
            "type": "other",
            "input_types": ["Data", "Message"],
            "value": None,
        }
        old["outputs"] = [
            {"name": "task", "types": ["Message"]},
            {"name": "pr", "types": ["Data"]},
            {"name": "operation_result", "types": ["Data"]},
        ]
        self.agent = {
            "id": "agent",
            "data": {
                "type": "LaomedoCodexAgent",
                "node": {
                    "template": {
                        "task": {
                            "type": "str",
                            "input_types": ["Message"],
                            "value": "saved instructions",
                        }
                    }
                },
            },
            "position": {"x": 300, "y": 50},
        }
        self.flow = {
            "name": "Keep this",
            "data": {
                "nodes": [self.pr, self.agent],
                "edges": [],
                "viewport": {"x": 12, "y": 13, "zoom": 0.75},
            },
            "custom": {"preserved": True},
        }

    def edge(self, source, name, target, field):
        a = {"id": source, "name": name, "output_types": ["Message"]}
        b = {"id": target, "fieldName": field, "inputTypes": ["Message"], "type": "str"}
        return {
            "id": "preserve-edge-id",
            "source": source,
            "target": target,
            "sourceHandle": json.dumps(a),
            "targetHandle": json.dumps(b),
            "data": {"sourceHandle": a, "targetHandle": b},
            "style": {"preserved": True},
        }

    def test_task_edge_migrates_with_all_unrelated_values_and_original_intact(self):
        self.flow["data"]["edges"] = [self.edge("pr", "task", "agent", "task")]
        original = copy.deepcopy(self.flow)
        result = migrate_pr_graph(self.flow, self.definition)
        self.assertEqual(self.flow, original)
        self.assertEqual(result["custom"], original["custom"])
        self.assertEqual(result["data"]["viewport"], original["data"]["viewport"])
        self.assertEqual(result["data"]["nodes"][0]["position"], self.pr["position"])
        template = result["data"]["nodes"][0]["data"]["node"]["template"]
        for name in ["repository_url", "pr_choice", "state", "labels"]:
            self.assertEqual(
                template[name]["value"], self.definition["template"][name]["value"]
            )
        self.assertNotIn("operation", template)
        self.assertNotIn("pr_reference", template)
        edge = result["data"]["edges"][0]
        self.assertEqual(json.loads(edge["sourceHandle"])["name"], "pr")
        self.assertEqual(json.loads(edge["sourceHandle"])["output_types"], ["Data"])
        self.assertEqual(edge["style"], original["data"]["edges"][0]["style"])
        self.assertEqual(
            result["data"]["nodes"][1]["data"]["node"]["template"]["task"]["value"],
            "saved instructions",
        )

    def test_two_incoming_edges_and_incompatible_consumers_refuse_without_mutation(
        self,
    ):
        cases = [
            [
                self.edge("agent", "answer", "pr", "operation"),
                self.edge("agent", "pr_context", "pr", "pr_reference"),
            ],
            [self.edge("pr", "task", "pr", "operation")],
            [self.edge("pr", "pr", "agent", "task")],
        ]
        for edges in cases:
            self.flow["data"]["edges"] = edges
            original = copy.deepcopy(self.flow)
            with self.assertRaisesRegex(ValueError, "pr_context_migration_required"):
                migrate_pr_graph(self.flow, self.definition)
            self.assertEqual(self.flow, original)

    def test_inline_identity_and_operation_coalesce_without_grant_invention(self):
        template = self.pr["data"]["node"]["template"]
        template["pr_reference"]["value"] = {"repository": "owner/repo", "number": 1}
        template["operation"]["value"] = {
            "action": "close",
            "request_id": "once",
            "grant_ref": "existing-host-ref",
        }
        result = migrate_pr_graph(self.flow, self.definition)
        value = result["data"]["nodes"][0]["data"]["node"]["template"]["pr_context"][
            "value"
        ]
        self.assertEqual(value["pr"], template["pr_reference"]["value"])
        self.assertEqual(value["operation"], template["operation"]["value"])

    def test_edited_code_requires_manual_migration(self):
        self.pr["data"]["node"]["edited"] = True
        with self.assertRaisesRegex(ValueError, "pr_context_migration_required"):
            migrate_pr_graph(self.flow, self.definition)
