"""Actual FastMCP HTTP transport and host-authority controls, without model inference."""

from contextlib import asynccontextmanager
import asyncio
from datetime import timedelta
import socket
import threading
import time
import unittest
from uuid import uuid4

from fastapi import FastAPI
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
import uvicorn

from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.mcp import AuthoringMcp
from laomedo.integrations.langflow.assistant.models import AuthoringContext
from laomedo.agents.mcp.models import McpTool


class AuthoringControl:
    """Own deliberately inert domain responses behind a real native MCP transport."""

    def __init__(self):
        self.context = AuthoringContext(
            owner_id=uuid4(),
            conversation_id=uuid4(),
            message_id=uuid4(),
            attempt_id=uuid4(),
            session_key="fixture-session-hash",
        )
        self.tool_tasks = {}
        self.revoked = False
        self.token = "x" * 43
        self.transport = None
        self.saved = []

    async def host_context(self, token):
        if token != self.token or self.revoked:
            raise AssistantError("assistant_tool_authority_revoked", 401)
        return self.context

    async def authorize(self, context):
        if self.revoked or context != self.context:
            raise AssistantError("assistant_tool_authority_revoked", 403)

    async def workflow_tools(self, context):
        await self.authorize(context)
        return self

    async def list(self, context, query="", cursor=0):
        return {
            "workflows": [
                {"workflow_id": str(uuid4()), "name": query or "Fixture draft"}
            ],
            "next_cursor": None,
        }

    async def save(self, context, workflows, request):
        self.saved.append(request)
        return {
            "draft_key": request.draft_key,
            "name": request.name,
            "workflow_id": str(uuid4()),
        }

    @asynccontextmanager
    async def lifespan(self, app):
        async with self.transport.server.session_manager.run():
            yield


class McpTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen()
        self.origin = "http://127.0.0.1:" + str(self.listener.getsockname()[1])
        self.control = AuthoringControl()
        self.control.transport = AuthoringMcp(self.control, self.origin)
        app = FastAPI(lifespan=self.control.lifespan)
        app.mount("/mcp", self.control.transport)
        self.server = uvicorn.Server(
            uvicorn.Config(app, log_level="error", access_log=False, lifespan="on")
        )
        self.thread = threading.Thread(
            target=self.server.run, kwargs={"sockets": [self.listener]}, daemon=True
        )
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        self.assertTrue(self.server.started)

    async def asyncTearDown(self):
        self.server.should_exit = True
        await asyncio.to_thread(self.thread.join, 10)
        self.listener.close()
        self.assertFalse(self.thread.is_alive())

    async def test_actual_protocol_discovery_and_nested_declarative_save(self):
        async with streamablehttp_client(
            self.origin + "/mcp/",
            headers={"Authorization": "Bearer " + self.control.token},
            timeout=timedelta(seconds=10),
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                self.assertEqual(
                    {tool.name for tool in tools},
                    {
                        "list_project_files",
                        "read_project_file",
                        "write_agent_file",
                        "list_workflows",
                        "get_workflow",
                        "search_components",
                        "describe_component",
                        "list_skills",
                        "save_draft",
                        "propose_graph_edit",
                        "propose_graph_run",
                        "get_graph_action",
                        "list_native_commands",
                        "list_native_agents",
                        "propose_native_command",
                        "get_native_action",
                    },
                )
                for tool in tools:
                    alias = McpTool(
                        server="laomedo",
                        upstream_name=tool.name,
                        display_name=tool.name,
                        description=tool.description or "",
                        input_schema=tool.inputSchema,
                    ).external_name()
                    self.assertEqual(
                        self.control.transport.display_names()[alias], tool.name
                    )
                    self.assertTrue(
                        {
                            "owner",
                            "owner_id",
                            "conversation_id",
                            "ctx",
                            "credential",
                            "server_url",
                        }.isdisjoint(tool.inputSchema.get("properties", {}))
                    )
                result = await session.call_tool(
                    "list_workflows", {"query": "Inspect this"}
                )
                self.assertFalse(result.isError)
                self.assertIn("Inspect this", result.content[0].text)
                native_agents = await session.call_tool("list_native_agents", {})
                self.assertFalse(native_agents.isError)
                self.assertIn("unsupported", native_agents.content[0].text)
                self.assertFalse(
                    any(
                        "approve" in tool.name or "execute_native" in tool.name
                        for tool in tools
                    )
                )
                invalid = await session.call_tool(
                    "propose_native_command",
                    {
                        "command": "status",
                        "arguments": "private-invalid\nargument",
                        "catalog_revision": "0" * 64,
                        "operation_key": "invalid-arguments",
                    },
                )
                self.assertTrue(invalid.isError)
                self.assertIn("assistant_input_invalid", invalid.content[0].text)
                self.assertNotIn("private-invalid", invalid.content[0].text)
                saved = await session.call_tool(
                    "save_draft",
                    {
                        "draft_key": "operation-1",
                        "name": "A real MCP call",
                        "spec": {
                            "nodes": [
                                {
                                    "key": "first",
                                    "component_type": "test/Text",
                                    "fields": {"text": "hello"},
                                }
                            ]
                        },
                    },
                )
                self.assertFalse(saved.isError, saved)
                self.assertEqual(
                    self.control.saved[0].spec.nodes[0].fields, {"text": "hello"}
                )
                self.assertFalse(
                    self.control.tool_tasks[self.control.context.message_id]
                )

    async def test_invalid_host_credential_and_dns_rebinding_refuse(self):
        import httpx

        async with httpx.AsyncClient() as client:
            denied = await client.post(
                self.origin + "/mcp/",
                json={},
                headers={"Authorization": "Bearer invalid"},
            )
            self.assertEqual(denied.status_code, 401)
            denied = await client.post(
                self.origin + "/mcp/",
                json={},
                headers={
                    "Authorization": "Bearer " + self.control.token,
                    "Host": "attacker.invalid",
                },
            )
            self.assertEqual(denied.status_code, 421)

    async def test_actual_project_file_tools_persist_and_refuse_revoked_authority(self):
        from pathlib import Path
        import json
        import tempfile
        from laomedo.integrations.langflow.assistant.storage.files import ProjectStorage
        from laomedo.integrations.langflow.assistant.storage.models import (
            RepositoryLocation,
            RepositoryRegistration,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "repo" / ".git").mkdir(parents=True)
            files = ProjectStorage(root / "state")
            owner = self.control.context.owner_id
            files.register(
                owner, RepositoryRegistration(name="Project", path=str(root / "repo"))
            )
            files.configure_agent_files(
                owner,
                RepositoryLocation(
                    repository_id=files.document(owner).repositories[0].id,
                    path="agent-files",
                ),
            )
            self.control.project_storage = files
            async with streamablehttp_client(
                self.origin + "/mcp/",
                headers={"Authorization": "Bearer " + self.control.token},
                timeout=timedelta(seconds=10),
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "write_agent_file",
                        {
                            "path": "notes.md",
                            "content": "Persistent project note",
                            "expected_sha256": None,
                        },
                    )
                    self.assertFalse(result.isError)
                    result = await session.call_tool(
                        "read_project_file", {"path": "notes.md"}
                    )
                    self.assertFalse(result.isError)
                    self.assertIn("Persistent project note", result.content[0].text)
                    stale = await session.call_tool(
                        "write_agent_file",
                        {
                            "path": "notes.md",
                            "content": "Wrong overwrite",
                            "expected_sha256": None,
                        },
                    )
                    self.assertTrue(stale.isError)
                    escaped = await session.call_tool(
                        "read_project_file", {"path": "../.git/config"}
                    )
                    self.assertTrue(escaped.isError)
            self.control.revoked = True
            import httpx

            async with httpx.AsyncClient() as client:
                denied = await client.post(
                    self.origin + "/mcp/",
                    headers={"Authorization": "Bearer " + self.control.token},
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "write_agent_file",
                            "arguments": {
                                "path": "notes.md",
                                "content": "Revoked",
                                "expected_sha256": None,
                            },
                        },
                    },
                )
                self.assertEqual(denied.status_code, 401)
            self.assertEqual(
                (root / "repo/agent-files/notes.md").read_text(),
                "Persistent project note",
            )
