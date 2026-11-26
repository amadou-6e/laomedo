"""Metadata-only compilation and explicit field/port/secret boundaries."""

import json
import unittest
from pathlib import Path

from laomedo.integrations.langflow.assistant.catalog import ComponentCatalog
from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.models import DraftGraph


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {
            "test": {
                "Text": {
                    "display_name": "Text",
                    "template": {
                        "code": {"value": "TRUSTED_INSTALLED_CODE"},
                        "text": {"type": "str", "required": True, "value": ""},
                        "api_key": {
                            "type": "str",
                            "password": True,
                            "value": "SECRET_CANARY",
                        },
                        "dynamic": {
                            "type": "str",
                            "real_time_refresh": True,
                            "value": "PRIVATE_DYNAMIC_CANARY",
                        },
                    },
                    "outputs": [{"name": "message", "types": ["Message"]}],
                },
                "Sink": {
                    "template": {
                        "code": {"value": "TRUSTED_SINK"},
                        "input_value": {
                            "type": "str",
                            "input_types": ["Message"],
                            "required": True,
                        },
                    },
                    "outputs": [],
                },
            }
        }
        self.catalog = ComponentCatalog(self.snapshot)
        self.graph = {
            "allow_incomplete": True,
            "nodes": [
                {
                    "key": "text",
                    "component_type": "test/Text",
                    "fields": {"text": "Hello"},
                },
                {"key": "sink", "component_type": "test/Sink"},
            ],
            "edges": [
                {
                    "source": "text",
                    "output": "message",
                    "target": "sink",
                    "input": "input_value",
                }
            ],
        }

    def test_compiles_exact_ports_using_only_trusted_templates(self):
        data, diagnostics = self.catalog.compile(DraftGraph.model_validate(self.graph))
        self.assertEqual(len(diagnostics), 2)
        self.assertTrue(any("api_key" in item for item in diagnostics))
        self.assertTrue(any("dynamic" in item for item in diagnostics))
        self.assertEqual(
            data["nodes"][0]["data"]["node"]["template"]["code"]["value"],
            "TRUSTED_INSTALLED_CODE",
        )
        self.assertEqual(
            data["edges"][0]["data"]["targetHandle"]["inputTypes"], ["Message"]
        )
        self.assertNotIn("SECRET_CANARY", json.dumps(data))
        self.assertNotIn("PRIVATE_DYNAMIC_CANARY", json.dumps(data))
        description = self.catalog.describe("test/Text")
        self.assertNotIn("TRUSTED_INSTALLED_CODE", json.dumps(description))
        self.assertNotIn("SECRET_CANARY", json.dumps(description))
        projected = self.catalog.project(data)
        self.assertEqual(projected["nodes"][0]["fields"], {"text": "Hello"})

    def test_unwritable_secret_code_and_dynamic_fields_refuse(self):
        for name in ("code", "api_key", "dynamic"):
            with (
                self.subTest(name=name),
                self.assertRaisesRegex(AssistantError, "assistant_field_not_writable"),
            ):
                graph = DraftGraph.model_validate(self.graph)
                graph.nodes[0].fields[name] = "malicious"
                self.catalog.compile(graph)

    def test_wrong_ports_duplicate_nodes_and_missing_metadata_refuse(self):
        graph = DraftGraph.model_validate(self.graph)
        graph.edges[0].output = "invented"
        with self.assertRaisesRegex(AssistantError, "assistant_port_unknown"):
            self.catalog.compile(graph)
        graph = DraftGraph.model_validate(self.graph)
        graph.nodes.append(graph.nodes[0])
        with self.assertRaisesRegex(AssistantError, "assistant_duplicate_node"):
            self.catalog.compile(graph)
        with self.assertRaisesRegex(
            AssistantError, "assistant_component_metadata_unavailable"
        ):
            ComponentCatalog({"test": {"Lazy": {"lazy_loaded": True}}}).describe(
                "test/Lazy"
            )

    def test_incomplete_requires_explicit_request_and_reports_diagnostics(self):
        graph = DraftGraph.model_validate(self.graph)
        graph.edges = []
        graph.allow_incomplete = False
        with self.assertRaisesRegex(AssistantError, "assistant_draft_incomplete"):
            self.catalog.compile(graph)
        graph.allow_incomplete = True
        _, diagnostics = self.catalog.compile(graph)
        self.assertIn(
            "sink.input_value: required setting or connection missing", diagnostics
        )

    def test_source_projection_names_unresolved_settings_without_releasing_values(self):
        data = {
            "nodes": [
                {
                    "id": "original",
                    "data": {"type": "Text", "node": self.snapshot["test"]["Text"]},
                }
            ],
            "edges": [],
        }
        projected = self.catalog.project(data)
        self.assertEqual(
            set(projected["nodes"][0]["unresolved_fields"]), {"api_key", "dynamic"}
        )
        self.assertNotIn("SECRET_CANARY", json.dumps(projected))

    def test_hidden_fields_and_host_selectors_are_not_model_writable(self):
        for name, extra in (
            ("hidden_value", {"show": False}),
            ("base_url", {}),
            ("api_base", {}),
            ("endpoint", {}),
            ("proxy", {}),
        ):
            with self.subTest(name=name):
                self.snapshot["test"]["Text"]["template"][name] = {
                    "type": "str",
                    **extra,
                }
                graph = DraftGraph.model_validate(self.graph)
                graph.nodes[0].fields[name] = "attacker supplied"
                with self.assertRaisesRegex(
                    AssistantError, "assistant_field_not_writable"
                ):
                    self.catalog.compile(graph)

    def test_complete_graph_with_supported_metadata_needs_no_incomplete_override(self):
        self.snapshot["test"]["Text"]["template"]["api_key"]["value"] = None
        self.snapshot["test"]["Text"]["template"]["dynamic"]["value"] = None
        graph = DraftGraph.model_validate(self.graph)
        graph.allow_incomplete = False
        _, diagnostics = self.catalog.compile(graph)
        self.assertEqual(diagnostics, [])

    def test_agent_run_reference_connects_to_verified_review_input(self):
        root = Path(__file__).resolve().parents[3]
        components = {}
        for filename, kind in (
            ("codex.json", "LaomedoCodexAgent"),
            ("claude.json", "LaomedoClaudeAgent"),
        ):
            graph = json.loads(
                (root / "tests/test_agents/test_examples/data" / filename).read_text(
                    encoding="utf-8"
                )
            )
            components[kind] = next(
                node["data"]["node"]
                for node in graph["data"]["nodes"]
                if node["data"]["type"] == kind
            )
        catalog = ComponentCatalog({"laomedo": components})
        draft = DraftGraph.model_validate(
            {
                "allow_incomplete": True,
                "nodes": [
                    {"key": "codex", "component_type": "laomedo/LaomedoCodexAgent"},
                    {"key": "claude", "component_type": "laomedo/LaomedoClaudeAgent"},
                ],
                "edges": [
                    {
                        "source": "codex",
                        "output": "run",
                        "target": "claude",
                        "input": "verified_changes",
                    }
                ],
            }
        )
        data, _ = catalog.compile(draft)
        self.assertEqual(
            data["edges"][0]["data"]["targetHandle"]["fieldName"], "verified_changes"
        )
