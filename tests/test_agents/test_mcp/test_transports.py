"""Real local MCP transports for the native borrowing compatibility gate.

These exercise native LFX discovery and MCP invocation against an actual local
server. They are not model/provider or real editor acceptance.
"""

import asyncio
from importlib.util import find_spec
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace
import unittest
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

        stdio = MCPStdioClient(tool_execution_timeout=15)
        http = MCPStreamableHttpClient(tool_execution_timeout=15)
        try:

            async def build():
                """Return an adapter, retaining the native app-loop-owned client."""
                _, tools, _ = await update_tools("local", config, stdio, http)
                self.assertEqual([tool.name for tool in tools], ["echo"])
                return LangflowMcpTool(tools[0])

            adapter = await build()
            await asyncio.sleep(0)
            result = await adapter.invoke({"message": "native-roundtrip"}, timeout=15)
            self.assertFalse(result["isError"])
            self.assertEqual(result["content"][0]["text"], "native-roundtrip")
        finally:
            for client in (stdio, http):
                if client._connected:
                    await client.disconnect()
                manager = getattr(client, "_session_manager", None)
                if manager:
                    await manager.cleanup_all()

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
