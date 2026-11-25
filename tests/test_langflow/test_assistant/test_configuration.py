"""Current audited resolution, schema/resource fencing and no-hook readiness controls."""

import time
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

from laomedo.integrations.langflow.assistant.catalog import ComponentCatalog
from laomedo.integrations.langflow.assistant.configuration import WorkflowConfiguration
from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.models import (
    AuthoringContext,
    ConfigurationRequest,
    DraftGraph,
    DraftNode,
)


class ConfigurationTests(unittest.IsolatedAsyncioTestCase):
    """Use controlled owner catalogues; these are not provider-native acceptance."""

    def setUp(self):
        self.owner, self.connection = uuid4(), uuid4()
        self.context = AuthoringContext(
            owner_id=self.owner,
            conversation_id=uuid4(),
            message_id=uuid4(),
            attempt_id=uuid4(),
            session_key="owner-session",
        )
        self.runtime = SimpleNamespace(
            authorize=AsyncMock(),
            check_session=AsyncMock(),
            check_connection=Mock(),
            connections=AsyncMock(
                return_value={
                    "connections": [
                        {
                            "connection_id": str(self.connection),
                            "provider": "codex",
                            "generation": 1,
                            "label": "Test",
                            "lifecycle": "connected",
                        }
                    ]
                }
            ),
            models=AsyncMock(
                return_value={
                    "models": [{"id": "observed-model", "efforts": ["low", "high"]}]
                }
            ),
        )
        self.configuration = WorkflowConfiguration(self.runtime)
        self.identity = "laomedo/LaomedoCodexAgent"
        self.catalog = ComponentCatalog(
            {
                "laomedo": {
                    "LaomedoCodexAgent": {
                        "template": {
                            "code": {
                                "value": (
                                    Path(__file__).resolve().parents[3]
                                    / "components/laomedo/codex_agent.py"
                                ).read_text(encoding="utf-8")
                            },
                            "provider_connection": {
                                "type": "str",
                                "real_time_refresh": True,
                                "value": "PRIVATE_CACHED_CANARY",
                                "show": False,
                            },
                            "model": {
                                "type": "str",
                                "real_time_refresh": True,
                                "required": True,
                            },
                            "effort": {"type": "str", "required": True, "options": []},
                            "task": {"type": "str", "required": True},
                        },
                        "outputs": [{"name": "answer", "types": ["Message"]}],
                    }
                }
            }
        )

    async def resolved(self):
        return await self.configuration.resolve(
            self.context,
            self.catalog,
            ConfigurationRequest(
                component_type=self.identity,
                connection_id=self.connection,
                connection_generation=1,
                fields={"task": "test", "model": "observed-model", "effort": "low"},
            ),
        )

    async def test_resolved_dependent_values_compile_without_copying_private_defaults(
        self,
    ):
        result = await self.resolved()
        node = DraftNode(
            key="agent",
            component_type=self.identity,
            fields=result["fields"],
            resolution_id=UUID(result["resolution_id"]),
        )
        await self.configuration.prepare(self.context, self.catalog, [node])
        data, messages = self.catalog.compile(DraftGraph(nodes=[node]))
        template = data["nodes"][0]["data"]["node"]["template"]
        self.assertEqual(template["model"]["value"], "observed-model")
        self.assertEqual(template["provider_connection"]["value"], str(self.connection))
        self.assertNotIn("PRIVATE_CACHED_CANARY", str(data))
        self.assertTrue(all(text.startswith("warning: ") for text in messages))
        self.runtime.models.assert_awaited_once_with(
            self.owner, "codex", self.connection, 1
        )

    async def test_partial_resolution_clears_unresolved_dependent_selectors(self):
        from laomedo.integrations.langflow.assistant.graph import GraphEditor
        from laomedo.integrations.langflow.assistant.models import (
            GraphChanges,
            GraphFieldUpdate,
        )

        complete = await self.resolved()
        node = DraftNode(
            key="agent",
            component_type=self.identity,
            fields=complete["fields"],
            resolution_id=UUID(complete["resolution_id"]),
        )
        await self.configuration.prepare(self.context, self.catalog, [node])
        data, _ = self.catalog.compile(DraftGraph(nodes=[node]))
        for fields, missing in (
            ({}, {"model", "effort"}),
            ({"model": "observed-model"}, {"effort"}),
        ):
            with self.subTest(fields=fields):
                partial = await self.configuration.resolve(
                    self.context,
                    self.catalog,
                    ConfigurationRequest(
                        component_type=self.identity,
                        connection_id=self.connection,
                        connection_generation=1,
                        fields=fields,
                    ),
                )
                update = GraphFieldUpdate(
                    node_id="LaomedoCodexAgent-agent",
                    fields=partial["fields"],
                    resolution_id=UUID(partial["resolution_id"]),
                )
                await self.configuration.prepare(self.context, self.catalog, [update])
                changed, _ = GraphEditor(self.catalog).apply(
                    data, GraphChanges(updates=[update])
                )
                template = changed["nodes"][0]["data"]["node"]["template"]
                for name in missing:
                    self.assertIsNone(template[name]["value"])
                self.assertEqual(template["task"]["value"], "test")
                self.assertEqual(
                    data["nodes"][0]["data"]["node"]["template"]["effort"]["value"],
                    "low",
                )

    async def test_namespaced_installed_adapter_resolves_with_its_exact_source_digest(
        self,
    ):
        component = self.catalog.snapshot["laomedo"].pop("LaomedoCodexAgent")
        name = "ext:laomedo:LaomedoCodexAgent@extra"
        component.update(name="LaomedoCodexAgent", namespaced_id=name)
        self.catalog.snapshot["laomedo"][name] = component
        self.identity = "laomedo/" + name
        result = await self.resolved()
        self.assertEqual(
            self.catalog.audited_family(self.identity), "LaomedoCodexAgent"
        )
        self.assertEqual(result["fields"]["provider_connection"], str(self.connection))
        description = self.catalog.describe(self.identity)
        self.assertEqual(description["configuration_support"], "audited_adapter")
        node = DraftNode(
            key="agent",
            component_type=self.identity,
            fields=result["fields"],
            resolution_id=UUID(result["resolution_id"]),
        )
        await self.configuration.prepare(self.context, self.catalog, [node])
        data, _ = self.catalog.compile(DraftGraph(nodes=[node]))
        self.assertEqual(data["nodes"][0]["data"]["type"], name)
        component["template"]["code"]["value"] += "\n# unreviewed change"
        self.assertIsNone(self.catalog.audited_family(self.identity))

    async def test_missing_account_never_discovers_models_or_selects_an_ambient_default(
        self,
    ):
        result = await self.configuration.resolve(
            self.context,
            self.catalog,
            ConfigurationRequest(component_type=self.identity),
        )
        self.assertNotIn("provider_connection", result["fields"])
        self.assertEqual(
            {issue["field"] for issue in result["remaining_requirements"]},
            {"provider_connection", "model", "effort", "task"},
        )
        self.runtime.models.assert_not_awaited()

    async def test_unknown_model_and_unsupported_effort_refuse(self):
        for fields in (
            {"model": "invented"},
            {"model": "observed-model", "effort": "invented"},
        ):
            with self.subTest(fields=fields), self.assertRaises(AssistantError):
                await self.configuration.resolve(
                    self.context,
                    self.catalog,
                    ConfigurationRequest(
                        component_type=self.identity,
                        connection_id=self.connection,
                        connection_generation=1,
                        fields=fields,
                    ),
                )

    async def test_schema_expiry_owner_and_generation_changes_fence_resolutions(self):
        result = await self.resolved()
        identifier = UUID(result["resolution_id"])
        resolved = self.configuration.resolutions[identifier]
        for changed in (
            {"expires_at": time.time() - 1},
            {"owner_id": uuid4()},
            {"session_key": "different"},
            {"schema_revision": "sha256:" + "0" * 64},
        ):
            with self.subTest(changed=changed), self.assertRaises(AssistantError):
                await self.configuration.check(
                    self.context, self.catalog, resolved.model_copy(update=changed)
                )
        self.runtime.check_connection.side_effect = AssistantError(
            "provider_connection_changed"
        )
        with self.assertRaises(AssistantError):
            await self.configuration.check(self.context, self.catalog, resolved)

    async def test_resolved_fields_cannot_be_changed_under_the_same_reference(self):
        result = await self.resolved()
        node = DraftNode(
            key="agent",
            component_type=self.identity,
            fields={**result["fields"], "model": "different"},
            resolution_id=UUID(result["resolution_id"]),
        )
        await self.configuration.prepare(self.context, self.catalog, [node])
        with self.assertRaisesRegex(AssistantError, "assistant_configuration_stale"):
            self.catalog.compile(DraftGraph(nodes=[node]))

    async def test_no_execution_validation_reports_required_fields(self):
        workflows = SimpleNamespace(catalog=self.catalog)
        result = await self.configuration.validate(
            self.context,
            workflows,
            spec=DraftGraph(
                nodes=[DraftNode(key="agent", component_type=self.identity)]
            ),
        )
        self.assertFalse(result["ready"])
        self.assertTrue(
            any(
                item["code"] == "required_input_missing"
                for item in result["diagnostics"]
            )
        )
        self.runtime.models.assert_not_awaited()

    async def test_protected_endpoints_and_unknown_fields_remain_denied(self):
        self.catalog.snapshot["laomedo"]["LaomedoCodexAgent"]["template"][
            "runner_url"
        ] = {"type": "str"}
        with self.assertRaisesRegex(AssistantError, "assistant_field_not_writable"):
            await self.configuration.resolve(
                self.context,
                self.catalog,
                ConfigurationRequest(
                    component_type=self.identity,
                    fields={"runner_url": "http://untrusted"},
                ),
            )

    async def test_retained_output_fences_recheck_connection_and_resource_epochs(self):
        result = await self.resolved()
        node = DraftNode(
            key="agent",
            component_type=self.identity,
            fields=result["fields"],
            resolution_id=UUID(result["resolution_id"]),
        )
        await self.configuration.prepare(self.context, self.catalog, [node])
        data, _ = self.catalog.compile(DraftGraph(nodes=[node]))
        bindings = self.configuration.graph_bindings(self.catalog, data)
        self.assertEqual(bindings[0]["binding"]["connection_id"], str(self.connection))
        await self.configuration.check_bindings(self.context, self.catalog, bindings)
        self.runtime.check_connection.side_effect = AssistantError(
            "provider_connection_changed"
        )
        with self.assertRaisesRegex(AssistantError, "provider_connection_changed"):
            await self.configuration.check_bindings(
                self.context, self.catalog, bindings
            )

    async def test_same_named_component_with_changed_source_is_not_an_audited_adapter(
        self,
    ):
        self.catalog.snapshot["laomedo"]["LaomedoCodexAgent"]["template"]["code"][
            "value"
        ] += "\n# changed implementation"
        self.assertIsNone(self.catalog.audited_family(self.identity))
        with self.assertRaises(AssistantError):
            await self.resolved()

    async def test_resolution_values_cannot_be_borrowed_by_an_unbound_second_node(self):
        result = await self.resolved()
        bound = DraftNode(
            key="bound",
            component_type=self.identity,
            fields=result["fields"],
            resolution_id=UUID(result["resolution_id"]),
        )
        unbound = DraftNode(
            key="unbound", component_type=self.identity, fields=result["fields"]
        )
        await self.configuration.prepare(self.context, self.catalog, [bound, unbound])
        with self.assertRaisesRegex(AssistantError, "assistant_field_not_writable"):
            self.catalog.compile(DraftGraph(nodes=[bound, unbound]))

    async def test_effort_requires_an_observed_selected_model(self):
        with self.assertRaisesRegex(AssistantError, "assistant_configuration_required"):
            await self.configuration.resolve(
                self.context,
                self.catalog,
                ConfigurationRequest(
                    component_type=self.identity,
                    connection_id=self.connection,
                    connection_generation=1,
                    fields={"effort": "unobserved"},
                ),
            )

    async def test_empty_native_effort_dropdown_does_not_admit_unresolved_extra_values(
        self,
    ):
        self.catalog.snapshot["laomedo"]["LaomedoCodexAgent"]["template"][
            "effort"
        ].update(show=True, real_time_refresh=False, dynamic=False, options=[])
        result = await self.configuration.resolve(
            self.context,
            self.catalog,
            ConfigurationRequest(
                component_type=self.identity,
                connection_id=self.connection,
                connection_generation=1,
                fields={"model": "observed-model"},
            ),
        )
        node = DraftNode(
            key="agent",
            component_type=self.identity,
            fields={**result["fields"], "effort": "invented"},
            resolution_id=UUID(result["resolution_id"]),
        )
        await self.configuration.prepare(self.context, self.catalog, [node])
        with self.assertRaisesRegex(AssistantError, "assistant_field_not_writable"):
            self.catalog.compile(DraftGraph(nodes=[node]))

    async def test_stale_binding_remains_inspectable_and_repairable_but_cannot_run(
        self,
    ):
        from laomedo.integrations.langflow.assistant.graph import GraphEditor
        from laomedo.integrations.langflow.assistant.models import (
            GraphChanges,
            GraphFieldUpdate,
        )

        resolved = await self.resolved()
        node = DraftNode(
            key="agent",
            component_type=self.identity,
            fields=resolved["fields"],
            resolution_id=UUID(resolved["resolution_id"]),
        )
        await self.configuration.prepare(self.context, self.catalog, [node])
        data, _ = self.catalog.compile(DraftGraph(nodes=[node]))
        self.runtime.check_connection.side_effect = AssistantError(
            "provider_connection_changed"
        )
        projected = await self.configuration.project(self.context, self.catalog, data)
        self.assertEqual(
            projected["diagnostics"][0]["node_id"], "LaomedoCodexAgent-agent"
        )
        self.assertEqual(projected["diagnostics"][0]["code"], "binding_stale")
        self.assertEqual(projected["nodes"][0]["fields"]["task"], "test")
        for field in ("provider_connection", "model", "effort"):
            self.assertNotIn(field, projected["nodes"][0]["fields"])
        with self.assertRaises(AssistantError):
            await self.configuration.check_graph(self.context, self.catalog, data)
        self.runtime.check_connection.side_effect = None
        fresh = await self.resolved()
        update = GraphFieldUpdate(
            node_id="LaomedoCodexAgent-agent",
            fields=fresh["fields"],
            resolution_id=UUID(fresh["resolution_id"]),
        )
        await self.configuration.prepare(self.context, self.catalog, [update])
        repaired, _ = GraphEditor(self.catalog).apply(
            data, GraphChanges(updates=[update])
        )
        self.assertEqual(
            await self.configuration.binding_diagnostics(
                self.context, self.catalog, repaired
            ),
            [],
        )
