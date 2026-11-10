"""Real local MCP transports for the native borrowing compatibility gate.

These exercise native LFX discovery and MCP invocation against an actual local
server. They are not model/provider or real editor acceptance.
"""

import asyncio
from contextlib import asynccontextmanager
from importlib.util import find_spec
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from uuid import uuid4
from unittest.mock import patch


@unittest.skipUnless(find_spec("lfx"), "Requires optional Langflow deployment")
class NativeTransportTests(unittest.IsolatedAsyncioTestCase):
    """Borrow actual STDIO/HTTP sessions while leaving client cleanup to its owner."""

    async def asyncSetUp(self):
        """Supply explicit non-secret service settings for standalone native clients."""
        self.config = patch(
            "lfx.base.mcp.util._get_mcp_setting",
            side_effect=lambda key, default=None: {
                "mcp_server_timeout": 15,
                "mcp_max_sessions_per_server": 4,
                "mcp_session_idle_timeout": 300,
                "mcp_session_cleanup_interval": 60,
            }.get(key, default),
        )
        self.config.start()
        self.addCleanup(self.config.stop)
        local_settings = SimpleNamespace(
            mcp_server_timeout=15, ssrf_protection_enabled=False
        )
        for target in (
            "lfx.base.mcp.util.get_settings_service",
            "lfx.utils.ssrf_protection.get_settings_service",
        ):
            configured = patch(
                target, return_value=SimpleNamespace(settings=local_settings)
            )
            configured.start()
            self.addCleanup(configured.stop)
        self.resource = Path(__file__).parent / "resources" / "server.py"

    async def check_transport(self, config):
        """Discover real tools and call after the simulated build coroutine returns."""
        from lfx.base.mcp.util import (
            MCPStdioClient,
            MCPStreamableHttpClient,
            update_tools,
        )
        from laomedo.integrations.langflow.mcp import LangflowMcpTool
        from laomedo.agents.mcp.registry import McpRegistry
        from laomedo.agents.mcp.settings import McpSettings
        from laomedo.agents.mcp.client import McpAccess
        from laomedo.agents.errors import RunnerError
        from fastapi import FastAPI
        from mcp import ClientSession
        from mcp.shared.exceptions import McpError
        from mcp.client.streamable_http import streamablehttp_client

        stdio = MCPStdioClient(tool_execution_timeout=15)
        http = MCPStreamableHttpClient(tool_execution_timeout=15)
        try:

            async def build():
                """Return an adapter, retaining the native app-loop-owned client."""
                _, tools, _ = await update_tools("local", config, stdio, http)
                self.assertEqual([tool.name for tool in tools], ["echo"])
                return LangflowMcpTool(tools[0])

            with tempfile.TemporaryDirectory() as state:
                settings = McpSettings(
                    directory=Path(state) / "connections", controller_host="127.0.0.1"
                )
                app = FastAPI(lifespan=self.upstream_lifespan)
                registry = McpRegistry.install(app, settings)
                async with app.router.lifespan_context(app):
                    adapter = await build()
                    registration = registry.register([adapter])
                    await asyncio.sleep(0)
                    # build() has returned; app lifespan still owns the native client.
                    access = await asyncio.to_thread(
                        McpAccess,
                        str(registration.registration_id),
                        registration.manifest.model_dump(mode="json"),
                        settings=settings,
                    )
                    connection = access.connection
                    await asyncio.to_thread(access.claim, str(uuid4()))
                    with self.assertRaisesRegex(
                        RunnerError, "mcp_run_binding_mismatch"
                    ):
                        await asyncio.to_thread(access.claim, str(uuid4()))
                    self.assertNotIn("token", connection.model_dump())
                    self.assertNotIn(
                        connection.token.get_secret_value(), repr(connection)
                    )
                    self.assertEqual(
                        access.redact({"value": connection.token.get_secret_value()}),
                        {"value": "[redacted]"},
                    )
                    try:
                        async with streamablehttp_client(
                            connection.endpoint(),
                            headers={
                                "Authorization": "Bearer "
                                + connection.token.get_secret_value()
                            },
                        ) as (read, write, _):
                            async with ClientSession(read, write) as session:
                                await session.initialize()
                                listed = await session.list_tools()
                                self.assertEqual(
                                    [tool.name for tool in listed.tools],
                                    list(access.tool_names()),
                                )
                                result = await session.call_tool(
                                    access.tool_names()[0],
                                    {"message": "native-roundtrip"},
                                )
                                self.assertFalse(result.isError)
                                self.assertEqual(
                                    result.content[0].text, "native-roundtrip"
                                )
                                with self.assertRaisesRegex(
                                    McpError, "mcp_tool_not_selected"
                                ):
                                    await session.call_tool("not_selected", {})
                    finally:
                        await asyncio.to_thread(access.close)
                    self.assertFalse(registry.leases)
        finally:
            for client in (stdio, http):
                if client._connected:
                    await client.disconnect()
                manager = getattr(client, "_session_manager", None)
                if manager:
                    await manager.cleanup_all()

    @asynccontextmanager
    async def upstream_lifespan(self, app):
        """Observe composition without initializing unrelated Langflow services."""
        self.upstream_active = True
        try:
            yield
        finally:
            self.upstream_active = False

    async def test_stdio_native_discovery_and_invocation(self):
        """Use the actual native STDIO client and a credential-free local process."""
        await self.check_transport(
            {"command": sys.executable, "args": [str(self.resource)]}
        )

    async def test_http_native_discovery_and_invocation(self):
        """Use the actual native HTTP client and a loopback-only MCP server."""
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            port = reserved.getsockname()[1]
        process = subprocess.Popen(
            [sys.executable, str(self.resource), str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(150):
                if process.poll() is not None:
                    self.fail("Local MCP server exited before readiness")
                try:
                    reader, writer = await asyncio.open_connection("127.0.0.1", port)
                    writer.close()
                    await writer.wait_closed()
                    break
                except OSError:
                    await asyncio.sleep(0.1)
            else:
                self.fail("Local MCP server did not become ready")
            await self.check_transport({"url": f"http://127.0.0.1:{port}/mcp"})
        finally:
            process.terminate()
            await asyncio.to_thread(process.wait, 10)
