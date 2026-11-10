"""Version-checked borrowing of native MCP tools without LFX invocation retries."""

import asyncio
import hashlib
from importlib.metadata import version
from inspect import getclosurevars
import json
from pydantic import BaseModel

from laomedo.agents.mcp.errors import McpError
from laomedo.agents.mcp.models import McpTool
from laomedo.agents.mcp.settings import (
    SUPPORTED_LFX_VERSION,
    MAX_SCHEMA_BYTES,
    MAX_ARGUMENT_BYTES,
    MAX_RESULT_BYTES,
    CALL_TIMEOUT_SECONDS,
)


class LangflowMcpTool:
    """Borrow a selected LFX MCP client on its original loop, without owning it.

    This adapter is deliberately restricted to the inspected LFX version and
    closure layout. Unknown shapes fail admission instead of invoking an arbitrary
    Python callable. No client is patched, disconnected or invalidated here.
    """

    def __init__(self, tool):
        """Validate native provenance, original identity, schema and approval scope."""
        from lfx.base.mcp.util import (
            MCPStdioClient,
            MCPStreamableHttpClient,
            create_tool_coroutine,
        )

        if version("lfx") != SUPPORTED_LFX_VERSION:
            raise McpError("mcp_native_version_unsupported")
        coroutine = getattr(tool, "coroutine", None)
        if (
            getattr(coroutine, "__code__", None)
            is not create_tool_coroutine("", None, None).__code__
        ):
            raise McpError("mcp_native_tool_unsupported")
        closure = getclosurevars(coroutine).nonlocals
        if set(closure) != {"arg_schema", "client", "tool_name"}:
            raise McpError("mcp_native_tool_unsupported")
        client = closure["client"]
        metadata = getattr(tool, "metadata", None) or {}
        if (
            type(client) not in (MCPStdioClient, MCPStreamableHttpClient)
            or not isinstance(metadata.get("server_name"), str)
            or not metadata["server_name"]
            or not getattr(tool, "tags", None)
            or tool.tags[0] != closure["tool_name"]
            or getattr(tool, "args_schema", None) is not closure["arg_schema"]
        ):
            raise McpError("mcp_native_tool_unsupported")
        if metadata.get("approval_actions"):
            raise McpError("mcp_tool_approval_unsupported")
        self._client = client
        self._schema = closure["arg_schema"]
        self._loop = asyncio.get_running_loop()
        self._binding_digest = self._binding()
        self.descriptor = McpTool(
            server=metadata["server_name"],
            upstream_name=closure["tool_name"],
            display_name=tool.name,
            description=tool.description or "",
            input_schema=self._schema.model_json_schema(),
        )
        if len(json.dumps(self.descriptor.input_schema).encode()) > MAX_SCHEMA_BYTES:
            raise McpError("mcp_schema_too_large")

    def _binding(self) -> str:
        """Fingerprint private mutable client routing without exposing its contents."""
        parameters = self._client._connection_params
        if isinstance(parameters, BaseModel):
            parameters = parameters.model_dump(mode="json")
        material = json.dumps(
            [self._client._session_context, parameters],
            sort_keys=True,
        )
        return hashlib.sha256(material.encode()).hexdigest()

    async def invoke(
        self, arguments: dict, *, timeout: float = CALL_TIMEOUT_SECONDS
    ) -> dict:
        """Validate arguments and issue exactly one call; preserve MCP error results.

        A timeout or transport failure may have occurred after remote effects.
        Neither this adapter nor its caller may reconnect and replay that call.
        The borrowed session manager may establish a session before dispatch.
        """
        from lfx.base.mcp.util import (
            _convert_camel_case_to_snake_case,
            _normalize_arguments_for_mcp,
            _strip_none_recursive,
            create_input_schema_from_json_schema,
        )

        if asyncio.get_running_loop() is not self._loop:
            raise McpError("mcp_event_loop_mismatch")
        if (
            self._binding() != self._binding_digest
            or self._schema.model_json_schema() != self.descriptor.input_schema
        ):
            raise McpError("mcp_tool_binding_changed")
        if not isinstance(arguments, dict):
            raise McpError("mcp_arguments_invalid")
        if len(json.dumps(arguments).encode()) > MAX_ARGUMENT_BYTES:
            raise McpError("mcp_arguments_too_large")
        try:
            converted = _convert_camel_case_to_snake_case(arguments, self._schema)
            normalized = _normalize_arguments_for_mcp(
                converted, self._schema, self.descriptor.upstream_name
            )
            validated = self._schema.model_validate(normalized)
            payload = _strip_none_recursive(validated.model_dump(exclude_none=True))
        except Exception:
            raise McpError("mcp_arguments_invalid") from None
        try:
            session = await asyncio.wait_for(
                self._client._get_or_create_session(), timeout=timeout
            )
            current = None
            cursor = None
            seen = set()
            async with asyncio.timeout(timeout):
                for _ in range(32):
                    advertised = (
                        await session.list_tools(cursor=cursor)
                        if cursor is not None
                        else await session.list_tools()
                    )
                    current = next(
                        (
                            tool
                            for tool in advertised.tools
                            if tool.name == self.descriptor.upstream_name
                        ),
                        None,
                    )
                    if current is not None or not advertised.nextCursor:
                        break
                    cursor = advertised.nextCursor
                    if cursor in seen:
                        raise McpError("mcp_tool_binding_changed")
                    seen.add(cursor)
            if (
                current is None
                or create_input_schema_from_json_schema(
                    current.inputSchema
                ).model_json_schema()
                != self.descriptor.input_schema
            ):
                raise McpError("mcp_tool_binding_changed")
        except McpError:
            raise
        except Exception:
            raise McpError("mcp_connection_unavailable") from None
        try:
            result = await asyncio.wait_for(
                session.call_tool(self.descriptor.upstream_name, arguments=payload),
                timeout=timeout,
            )
        except Exception:
            raise McpError("mcp_call_outcome_unknown") from None
        response = result.model_dump(mode="json", exclude_none=True)
        if len(json.dumps(response).encode()) > MAX_RESULT_BYTES:
            raise McpError("mcp_result_too_large")
        return response
