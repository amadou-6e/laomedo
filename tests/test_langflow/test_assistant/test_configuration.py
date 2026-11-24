"""Current audited resolution, schema/resource fencing and no-hook readiness controls."""

import time
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
                            "code": {"value": "HOST_OWNED_ADAPTER"},
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

    async def test_missing_account_never_discovers_models_or_selects_an_ambient_default(
        self,
    ):
        result = await self.configuration.resolve(
            self.context,
            self.catalog,
            ConfigurationRequest(component_type=self.identity),
        )
        self.assertNotIn("provider_connection", result["fields"])
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
