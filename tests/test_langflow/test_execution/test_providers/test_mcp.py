"""Registered MCP boundaries with native metadata, SQL ownership and inert tools.

These checks do not submit a model task or establish live Agent acceptance.
"""

from contextlib import asynccontextmanager
import asyncio
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from langflow.services.database.models import MCPServer, User

from laomedo.agents.connections.models import (
    GraphNodePolicy,
    GraphRunNode,
    GraphRunPlan,
)
from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.mcp.errors import McpError
from laomedo.agents.mcp.models import McpManifest, McpRegistration, McpTool
from laomedo.integrations.langflow.assistant.catalog import ComponentCatalog
from laomedo.integrations.langflow.assistant.models import (
    DraftGraph,
    ResolvedConfiguration,
    ResourceBinding,
)
from laomedo.integrations.langflow.execution.providers.admission import (
    ProviderGraphAdmission,
)
from laomedo.integrations.langflow.execution.providers.catalog import (
    ProviderComponentCatalog,
)
from laomedo.integrations.langflow.execution.providers.mcp import (
    RegisteredMcpTools,
    RegisteredMcpTool,
)
from laomedo.integrations.langflow.execution.providers.models import GraphMcpSelection
from laomedo.integrations.langflow.graph_admission.catalog import GitHubGraphCatalog


class McpProjectionTests(unittest.TestCase):
    """The real authoring compiler selects MCP resources; workers receive no clients."""

    def test_native_compiler_projection_retains_host_binding_only(self):
        installed = ProviderComponentCatalog(
            Path(__file__).resolve().parents[4] / "components"
        )
        catalog = ComponentCatalog(installed._registry)
        owner, account, server = uuid4(), uuid4(), uuid4()
        definitions = []
        for key, kind, fields, resources in (
            (
                "tools",
                "MCPTools",
                {"mcp_server": {"name": "registered-fixture"}},
                [ResourceBinding(kind="mcp", id=str(server), version="3")],
            ),
            (
                "agent",
                "LaomedoCodexAgent",
                {"provider_connection": str(account), "model": "m", "effort": "low"},
                [],
            ),
        ):
            identity = "laomedo/" + kind
            resolution = ResolvedConfiguration(
                owner_id=owner,
                conversation_id=uuid4(),
                session_key="fixture",
                component_type=identity,
                schema_revision=catalog.schema_revision(identity),
                fields=fields,
                resources=resources,
                expires_at=time.time() + 60,
                connection_id=account if key == "agent" else None,
                connection_generation=1 if key == "agent" else None,
            )
            catalog.allow_resolution(resolution)
            definitions.append(
                {
                    "key": key,
                    "component_type": identity,
                    "resolution_id": resolution.id,
                    "fields": fields
                    | (
                        {"task": "Use the selected tools", "operation": "fresh"}
                        if key == "agent"
                        else {}
                    ),
                }
            )
        graph, _ = catalog.compile(
            DraftGraph.model_validate(
                {
                    "nodes": definitions,
                    "edges": [
                        {
                            "source": "tools",
                            "output": "component_as_tool",
                            "target": "agent",
                            "input": "mcp_tools",
                        }
                    ],
                }
            )
        )
        connections = Mock()
        connections._lock = threading.RLock()
        connections.admitted.return_value = SimpleNamespace(
            provider="codex", connection_id=account, generation=1
        )
        admission = ProviderGraphAdmission(connections, installed.admission)
        prepared = admission.prepare(owner, "lease", uuid4(), uuid4(), graph)
        self.assertEqual(prepared.mcps[0].binding.id, str(server))
        self.assertEqual(prepared.mcps[0].targets, ("LaomedoCodexAgent-agent",))
        self.assertNotEqual(
            prepared.plan.graph_digest, "sha256:" + prepared.job.graph_digest
        )
        worker = prepared.job.model_dump_json()
        for private in (
            str(server),
            "registered-fixture",
            "MCPTools",
            "laomedo_authoring_bindings",
            str(account),
        ):
            self.assertNotIn(private, worker)
        self.assertEqual(prepared.job.graph["edges"], [])
        self.assertEqual(len(prepared.job.graph["nodes"]), 1)
        self.assertIsNone(prepared.plan.nodes[0].policy.mcp_registration)
        self.assertNotIn(
            "MCPTools",
            {
                entry.classification
                for entry in GitHubGraphCatalog.capture(
                    installed._registry
                ).snapshot.entries
            },
        )
        for field, value in (
            ("mcp_server", {"name": "registered-fixture", "url": "http://private"}),
            ("headers", {"Authorization": "private"}),
            ("verify_ssl", False),
        ):
            changed = deepcopy(graph)
            changed["nodes"][0]["data"]["node"]["template"][field]["value"] = value
            with self.subTest(field=field), self.assertRaises(ProviderConnectionError):
                admission.prepare(owner, "lease", uuid4(), uuid4(), changed)

    def test_host_registration_is_not_worker_input_or_serializable_policy(self):
        registration = McpRegistration(
            registration_id=uuid4(),
            manifest=McpManifest(
                tools=(
                    McpTool(
                        server="fixture",
                        upstream_name="echo",
                        display_name="echo",
                        description="Echo",
                        input_schema={"type": "object", "properties": {}},
                    ),
                )
            ),
        )
        policy = GraphNodePolicy(
            model="m", effort="low", task="Read", mcp_registration=registration
        )
        body = {
            "request_id": str(uuid4()),
            "model": "m",
            "effort": "low",
            "task": "Read",
            "skill_refs": [],
        }
        native = policy.native_request(body, "host-id")
        self.assertEqual(native["mcp_registration"], str(registration.registration_id))
        self.assertNotIn(str(registration.registration_id), policy.model_dump_json())
        for field in ("mcp_registration", "mcp_manifest", "mcp_servers"):
            with self.subTest(field=field), self.assertRaises(ProviderConnectionError):
                policy.native_request({**body, field: native.get(field, [])}, "host-id")


class RegisteredMcpOwnershipTests(unittest.IsolatedAsyncioTestCase):
    """Real database ownership/version checks fence discovery, calls and release."""

    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///" + (Path(self.directory.name) / "app.db").as_posix()
        )
        self.addAsyncCleanup(self.engine.dispose)
        async with self.engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)
        self.profile, self.identifier = uuid4(), uuid4()
        self.selection = GraphMcpSelection(
            vertex_id="tools",
            name="fixture",
            binding=ResourceBinding(kind="mcp", id=str(self.identifier), version="1"),
            targets=("agent",),
        )
        self.plan = GraphRunPlan(
            profile_id=self.profile,
            lease_hash="lease",
            flow_id=uuid4(),
            graph_digest="sha256:" + "a" * 64,
            deadline=time.monotonic() + 60,
            nodes=(
                GraphRunNode(
                    vertex_id="agent",
                    provider="codex",
                    connection_id=uuid4(),
                    generation=1,
                    policy=GraphNodePolicy(model="m", effort="low", task="Read"),
                ),
            ),
        )
        self.connections = Mock()
        self.connections.admitted.return_value = SimpleNamespace(provider="codex")
        self.resources = RegisteredMcpTools(
            self.connections, SimpleNamespace(plan=self.plan, mcps=(self.selection,))
        )
        self.addAsyncCleanup(self.close_fixture)
        self.scope = patch("langflow.services.deps.session_scope", self.session)
        self.scope.start()
        self.addCleanup(self.scope.stop)
        async with self.session() as session:
            session.add(
                User(
                    id=self.profile, username="owner", password="unused", is_active=True
                )
            )
            session.add(
                MCPServer(
                    id=self.identifier,
                    user_id=self.profile,
                    name="fixture",
                    version=1,
                    config={
                        "url": "https://example.invalid/mcp",
                        "headers": {"Authorization": "PRIVATE_CONFIG_CANARY"},
                    },
                )
            )
            await session.commit()

    @asynccontextmanager
    async def session(self):
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            yield session

    async def close_fixture(self):
        from lfx.base.mcp.util import MCPStdioClient, MCPStreamableHttpClient

        with (
            patch.object(MCPStdioClient, "disconnect", new=AsyncMock()),
            patch.object(MCPStreamableHttpClient, "disconnect", new=AsyncMock()),
        ):
            await self.resources.close()

    async def test_metadata_check_never_decrypts_or_connects(self):
        with (
            patch(
                "langflow.services.auth.mcp_encryption.decrypt_mcp_config",
                side_effect=AssertionError("metadata must not decrypt"),
            ),
            patch(
                "lfx.base.mcp.util.update_tools",
                new=AsyncMock(side_effect=AssertionError("metadata must not connect")),
            ),
        ):
            await self.resources.check()
        self.connections.check_lease.assert_called_with("lease")
        async with self.session() as session:
            server = await session.get(MCPServer, self.identifier)
            server.version += 1
            await session.commit()
        with self.assertRaisesRegex(McpError, "mcp_registration_unavailable"):
            await self.resources.check()

    async def test_foreign_disabled_deleted_or_renamed_registration_refuses(self):
        for attribute, value in (
            ("user_id", uuid4()),
            ("enabled", False),
            ("name", "renamed"),
        ):
            async with self.session() as session:
                row = await session.get(MCPServer, self.identifier)
                original = getattr(row, attribute)
                setattr(row, attribute, value)
                await session.commit()
            with self.subTest(attribute=attribute), self.assertRaises(McpError):
                await self.resources.check()
            async with self.session() as session:
                row = await session.get(MCPServer, self.identifier)
                setattr(row, attribute, original)
                await session.commit()
        async with self.session() as session:
            await session.delete(await session.get(MCPServer, self.identifier))
            await session.commit()
        with self.assertRaises(McpError):
            await self.resources.check()

    async def test_tool_revocation_withholds_result_and_never_replays(self):
        adapter = SimpleNamespace(
            descriptor=Mock(), invoke=AsyncMock(return_value={"content": []})
        )
        with patch(
            "laomedo.integrations.langflow.execution.providers.mcp.LangflowMcpTool",
            return_value=adapter,
        ):
            tool = RegisteredMcpTool(self.resources, self.selection, object())

        async def invoke(arguments):
            async with self.session() as session:
                row = await session.get(MCPServer, self.identifier)
                row.enabled = False
                await session.commit()
            return {"content": []}

        adapter.invoke.side_effect = invoke
        with self.assertRaises(McpError):
            await tool.invoke({})
        adapter.invoke.assert_awaited_once_with({})
        with self.assertRaises(McpError):
            await tool.invoke({})
        adapter.invoke.assert_awaited_once()

    async def test_native_discovery_builds_exact_per_agent_grant_and_single_call(self):
        from lfx.base.mcp.util import MCPStreamableHttpClient
        from mcp.types import Tool, ListToolsResult, CallToolResult, TextContent

        advertised = Tool(
            name="echo",
            description="Echo",
            inputSchema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )
        registration = McpRegistration(
            registration_id=uuid4(),
            manifest=McpManifest(
                tools=(
                    McpTool(
                        server="fixture",
                        upstream_name="echo",
                        display_name="echo",
                        description="Echo",
                        input_schema=advertised.inputSchema,
                    ),
                )
            ),
        )
        registry = SimpleNamespace(
            register=AsyncMock(return_value=registration), release=Mock()
        )
        session = SimpleNamespace(
            list_tools=AsyncMock(return_value=ListToolsResult(tools=[advertised])),
            call_tool=AsyncMock(
                return_value=CallToolResult(
                    content=[TextContent(type="text", text="echoed")], isError=False
                )
            ),
        )

        async def connect(client, url, **kwargs):
            self.assertEqual(
                kwargs["headers"]["authorization"], "PRIVATE_CONFIG_CANARY"
            )
            client._connected = True
            client._connection_params = {"url": url}
            return [advertised]

        with (
            patch(
                "laomedo.integrations.langflow.execution.providers.mcp.McpRegistry.current",
                return_value=registry,
            ),
            patch(
                "langflow.services.auth.mcp_encryption.decrypt_mcp_config",
                side_effect=lambda value: value,
            ),
            patch(
                "langflow.services.deps.get_settings_service",
                return_value=SimpleNamespace(settings=SimpleNamespace()),
            ),
            patch.object(MCPStreamableHttpClient, "connect_to_server", new=connect),
            patch("lfx.base.mcp.util.validate_connector_url_for_ssrf") as ssrf,
            patch(
                "lfx.base.mcp.util.get_settings_service",
                return_value=SimpleNamespace(settings=SimpleNamespace()),
            ),
            patch.object(
                MCPStreamableHttpClient, "_terminate_remote_session", new=AsyncMock()
            ),
            patch(
                "langflow.services.deps.get_variable_service",
                return_value=SimpleNamespace(
                    get_all_decrypted_variables=AsyncMock(return_value={})
                ),
            ),
            patch.object(
                MCPStreamableHttpClient,
                "_get_or_create_session",
                new=AsyncMock(return_value=session),
            ),
        ):
            plan = await asyncio.wait_for(self.resources.prepare(), 30)
            ssrf.assert_called_once_with("https://example.invalid/mcp")
            tool = registry.register.call_args.args[0][0]
            self.assertIs(plan.nodes[0].policy.mcp_registration, registration)
            self.assertNotIn("PRIVATE_CONFIG_CANARY", plan.model_dump_json())
            self.assertEqual(
                (await tool.invoke({"text": "hello"}))["content"][0]["text"], "echoed"
            )
            session.call_tool.assert_awaited_once_with(
                "echo", arguments={"text": "hello"}
            )
            await self.resources.close()
        registry.release.assert_called_once_with(registration.registration_id)
        self.assertEqual(self.resources.clients, [])

    async def test_cleanup_revokes_all_grants_before_clients_and_can_retry(self):
        events = []
        identifier = uuid4()
        self.resources.registrations = [identifier]
        self.resources.registry = SimpleNamespace(
            release=Mock(side_effect=lambda _: events.append("revoked"))
        )
        client = SimpleNamespace(
            disconnect=AsyncMock(side_effect=OSError("PRIVATE_ERROR_CANARY"))
        )
        self.resources.clients = [client]
        with self.assertRaises(McpError):
            await self.resources.close()
        self.assertEqual(events, ["revoked"])
        self.assertEqual(self.resources.clients, [client])
        self.assertTrue(self.resources.closed)
        client.disconnect.side_effect = lambda: events.append("closed")
        await self.resources.close()
        self.assertEqual(events, ["revoked", "closed"])
        self.assertEqual(self.resources.clients, [])
        self.resources.registry.release.assert_called_once_with(identifier)
