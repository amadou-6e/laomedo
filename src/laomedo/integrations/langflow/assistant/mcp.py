"""Actual private FastMCP authoring tools, scoped by host credentials rather than arguments."""

import json
import asyncio
from urllib.parse import urlsplit
from uuid import UUID

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.settings import (
    AUTHORING_SERVER_NAME,
    AUTHORING_TOOL_NAMES,
)
from laomedo.agents.mcp.models import McpTool
from laomedo.integrations.langflow.assistant.models import (
    DraftGraph,
    DraftRequest,
    WorkflowSource,
)


class AuthoringMcp:
    """Expose six bounded tools; the public app API credential never enters a provider."""

    def __init__(self, runtime, origin):
        """Build a stateless HTTP app with explicit Host/origin protection and no model work."""
        self.runtime = runtime
        host = urlsplit(origin).netloc
        self.server = FastMCP(
            "Laomedo authoring",
            stateless_http=True,
            json_response=True,
            streamable_http_path="/",
            max_request_body_size=131072,
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=[host],
                allowed_origins=[origin],
            ),
        )
        for name in AUTHORING_TOOL_NAMES:
            self.server.add_tool(getattr(self, name), name=name)
        self.app = self.server.streamable_http_app()

    @staticmethod
    def display_names():
        """Resolve the fixed authoring aliases with the forwarding layer's canonical identity rule."""
        return {
            McpTool(
                server=AUTHORING_SERVER_NAME,
                upstream_name=name,
                display_name=name,
                description="",
                input_schema={},
            ).external_name(): name
            for name in AUTHORING_TOOL_NAMES
        }

    async def __call__(self, scope, receive, send):
        """Authenticate discovery as well as calls before entering MCP's protocol handler."""
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = [
            value.decode("latin-1")
            for key, value in scope["headers"]
            if key.lower() == b"authorization"
        ]
        try:
            if len(headers) != 1 or not headers[0].startswith("Bearer "):
                raise AssistantError("assistant_tool_authority_revoked", 401)
            context = await self.runtime.host_context(headers[0][7:])
        except AssistantError:
            return await JSONResponse(
                {"code": "assistant_tool_authority_revoked"}, status_code=401
            )(scope, receive, send)
        scope["laomedo_authoring"] = context
        return await self.app(scope, receive, send)

    async def _invoke(self, ctx, operation, **arguments):
        """Release bounded results only while the exact host binding remains authorized."""
        context = None
        task = asyncio.current_task()
        try:
            request = ctx.request_context.request
            context = request.scope.get("laomedo_authoring") if request else None
            if context is None:
                raise AssistantError("assistant_tool_authority_revoked", 403)
            self.runtime.tool_tasks.setdefault(context.message_id, set()).add(task)
            await self.runtime.authorize(context)
            if operation == "list_skills":
                result = await self.runtime.skills(context, **arguments)
            else:
                workflows = await self.runtime.workflow_tools(context)
                if operation == "list_workflows":
                    result = await workflows.list(context, **arguments)
                elif operation == "get_workflow":
                    result = await workflows.get(context, **arguments)
                elif operation == "search_components":
                    result = workflows.catalog.search(**arguments)
                elif operation == "describe_component":
                    result = workflows.catalog.describe(arguments["component_type"])
                else:
                    result = await self.runtime.save(
                        context, workflows, arguments["request"]
                    )
            await self.runtime.authorize(context)
            if len(json.dumps(result).encode()) > 524288:
                raise AssistantError("assistant_tool_result_too_large", 422)
            return result
        except AssistantError as error:
            raise ToolError(error.code) from None
        except Exception:
            raise ToolError("assistant_tool_unavailable") from None
        finally:
            if context is not None:
                self.runtime.tool_tasks.get(context.message_id, set()).discard(task)

    async def list_workflows(
        self, ctx: Context, query: str = "", cursor: int = 0
    ) -> dict:
        """List bounded saved workflow summaries belonging to this authenticated owner."""
        return await self._invoke(ctx, "list_workflows", query=query, cursor=cursor)

    async def get_workflow(self, workflow_id: UUID, ctx: Context) -> dict:
        """Inspect a saved workflow's revision and projected non-secret nodes/ports/settings."""
        return await self._invoke(ctx, "get_workflow", workflow_id=workflow_id)

    async def search_components(
        self, query: str, ctx: Context, cursor: int = 0
    ) -> dict:
        """Search authorized installed component identities; never load or execute component code."""
        return await self._invoke(ctx, "search_components", query=query, cursor=cursor)

    async def describe_component(self, component_type: str, ctx: Context) -> dict:
        """Describe exact installed inputs, outputs and writable static field schemas."""
        return await self._invoke(
            ctx, "describe_component", component_type=component_type
        )

    async def list_skills(self, ctx: Context, query: str = "", cursor: int = 0) -> dict:
        """List authorized imported local Skill identities, immutable revisions and descriptions."""
        return await self._invoke(ctx, "list_skills", query=query, cursor=cursor)

    async def save_draft(
        self,
        draft_key: str,
        name: str,
        spec: DraftGraph,
        ctx: Context,
        sources: list[WorkflowSource] | None = None,
        draft_id: UUID | None = None,
        expected_revision: str | None = None,
    ) -> dict:
        """Atomically save a declarative editable draft and receipt. Never run, publish, delete or overwrite source workflows. An edit needs your own draft_id, exact expected_revision and a new draft_key. An uncertain save must be reconciled, never repeated under a new key."""
        try:
            request = DraftRequest(
                draft_key=draft_key,
                name=name,
                spec=spec,
                sources=sources or [],
                draft_id=draft_id,
                expected_revision=expected_revision,
            )
        except ValueError:
            raise ToolError("assistant_input_invalid") from None
        return await self._invoke(ctx, "save_draft", request=request)
