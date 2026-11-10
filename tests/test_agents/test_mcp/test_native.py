"""Protect exact native compatibility and the no-replay invocation boundary.

These checks use actual LFX tool construction and MCP SDK result models, with
controlled transport responses. They do not establish real provider acceptance.
"""

import asyncio
from importlib.util import find_spec
import unittest
from unittest.mock import AsyncMock, patch

from laomedo.agents.mcp.errors import McpError
from laomedo.agents.mcp.models import McpManifest


@unittest.skipUnless(find_spec("lfx"), "Requires optional Langflow deployment")
class NativeToolTests(unittest.IsolatedAsyncioTestCase):
    """Exercise real native tool factories with deterministic transport outcomes."""

    async def asyncSetUp(self):
        """Build the exact installed native MCP tool class without a live server."""
        from lfx.base.mcp.util import (
            MCPStdioClient,
            MCPStreamableHttpClient,
            update_tools,
        )
        from mcp.types import CallToolResult, TextContent, Tool, ListToolsResult

        self.result = CallToolResult(content=[TextContent(type="text", text="result")])
        self.client = MCPStdioClient(tool_execution_timeout=180)
        self.client._connected = True
        native = Tool(
            name="echo",
            description="Read-only echo tool.",
            inputSchema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        )
        with patch.object(
            self.client, "connect_to_server", AsyncMock(return_value=[native])
        ):
            _, tools, _ = await update_tools(
                "example",
                {"command": "python", "args": []},
                self.client,
                MCPStreamableHttpClient(tool_execution_timeout=180),
            )
        self.tool = tools[0]
        self.call = AsyncMock(return_value=self.result)
        self.session = unittest.mock.Mock(
            call_tool=self.call,
            list_tools=AsyncMock(return_value=ListToolsResult(tools=[native])),
        )
        self.client._get_or_create_session = AsyncMock(return_value=self.session)

    async def test_alias_does_not_change_upstream_name_or_manifest_identity(self):
        """UI aliases retain exact original invocation names and stable manifests."""
        from laomedo.integrations.langflow.mcp import LangflowMcpTool

        self.tool.name = "renamed_echo"
        adapter = LangflowMcpTool(self.tool)
        response = await adapter.invoke({"message": "hello"})
        self.call.assert_awaited_once_with("echo", arguments={"message": "hello"})
        self.assertFalse(response["isError"])
        manifest = McpManifest(tools=(adapter.descriptor,))
        restored = McpManifest.model_validate_json(manifest.model_dump_json())
        self.assertEqual(manifest.digest(), restored.digest())
        self.assertTrue(adapter.descriptor.external_name().startswith("external_"))

    async def test_transport_failure_never_replays(self):
        """An uncertain dispatched call is attempted once, even for a timeout."""
        from laomedo.integrations.langflow.mcp import LangflowMcpTool

        self.call.side_effect = TimeoutError("private upstream failure")
        with self.assertRaisesRegex(McpError, "^mcp_call_outcome_unknown$"):
            await LangflowMcpTool(self.tool).invoke({"message": "hello"})
        self.assertEqual(self.call.await_count, 1)

    async def test_selected_tool_on_later_page_is_checked_before_dispatch(self):
        """Pagination must not incorrectly invalidate an unchanged selected tool."""
        from mcp.types import ListToolsResult
        from laomedo.integrations.langflow.mcp import LangflowMcpTool

        selected = self.session.list_tools.return_value
        self.session.list_tools.side_effect = [
            ListToolsResult(tools=[], nextCursor="next-page"),
            selected,
        ]
        await LangflowMcpTool(self.tool).invoke({"message": "hello"})
        self.session.list_tools.assert_awaited_with(cursor="next-page")
        self.call.assert_awaited_once()

    async def test_mcp_error_result_is_preserved(self):
        """Do not convert an upstream MCP error into apparent successful content."""
        from laomedo.integrations.langflow.mcp import LangflowMcpTool

        self.result.isError = True
        response = await LangflowMcpTool(self.tool).invoke({"message": "hello"})
        self.assertTrue(response["isError"])

    async def test_invalid_arguments_do_not_dispatch(self):
        """Validate native field types before borrowing or executing a tool."""
        from laomedo.integrations.langflow.mcp import LangflowMcpTool

        with self.assertRaisesRegex(McpError, "mcp_arguments_invalid"):
            await LangflowMcpTool(self.tool).invoke({"message": {}})
        self.call.assert_not_awaited()

    async def test_unsupported_approval_is_not_bypassed(self):
        """Refuse tools whose selected approval interaction cannot be preserved."""
        from laomedo.integrations.langflow.mcp import LangflowMcpTool

        self.tool.metadata["approval_actions"] = ["confirm"]
        with self.assertRaisesRegex(McpError, "mcp_tool_approval_unsupported"):
            LangflowMcpTool(self.tool)

    async def test_arbitrary_callable_cannot_enter_native_bridge(self):
        """A callable with MCP-looking metadata is not sufficient provenance."""
        from laomedo.integrations.langflow.mcp import LangflowMcpTool

        self.tool.coroutine = AsyncMock()
        with self.assertRaisesRegex(McpError, "mcp_native_tool_unsupported"):
            LangflowMcpTool(self.tool)
