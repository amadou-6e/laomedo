"""Job-owned native MCP sessions; connection configuration never enters a worker."""

import asyncio
import time
from uuid import UUID

from laomedo.agents.mcp.errors import McpError
from laomedo.agents.mcp.registry import McpRegistry
from laomedo.agents.mcp.settings import CALL_TIMEOUT_SECONDS
from laomedo.integrations.langflow.mcp import LangflowMcpTool


class RegisteredMcpTool:
    """Fence one audited native tool against the exact live owner and resource pin."""

    def __init__(self, owner, selection, tool):
        self.owner = owner
        self.selection = selection
        self.tool = LangflowMcpTool(tool)
        self.descriptor = self.tool.descriptor

    async def invoke(self, arguments):
        """Invoke once; revocation withholds results without replaying remote effects."""
        await self.owner.check(self.selection)
        result = await self.tool.invoke(arguments)
        await self.owner.check(self.selection)
        return result


class RegisteredMcpTools:
    """Own only this approved graph's clients, managers and per-Agent grants."""

    def __init__(self, connections, prepared):
        self.connections = connections
        self.plan = prepared.plan
        self.selections = prepared.mcps
        self.registry = None
        self.clients = []
        self.registrations = []
        self.maintenance = None
        self.closed = False
        self.loop = asyncio.get_running_loop()

    def check_dispatch(self):
        """Fence a worker-thread start on the original host loop, without discovery."""
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if current is self.loop:
            raise McpError("mcp_registration_unavailable")
        future = asyncio.run_coroutine_threadsafe(self.check(), self.loop)
        try:
            future.result(timeout=CALL_TIMEOUT_SECONDS)
        except BaseException:
            future.cancel()
            raise

    @staticmethod
    async def registered_row(session, profile_id, selection):
        """Resolve native rows by exact active owner and pin, never decrypt configuration."""
        from sqlmodel import select
        from langflow.services.database.models import MCPServer, User

        user = await session.get(User, profile_id)
        row = (
            await session.exec(
                select(MCPServer).where(
                    MCPServer.id == UUID(selection.binding.id),
                    MCPServer.user_id == profile_id,
                    MCPServer.name == selection.name,
                    MCPServer.enabled == True,
                    MCPServer.version == int(selection.binding.version),
                )
            )
        ).first()
        if user is None or not user.is_active or row is None:
            raise McpError("mcp_registration_unavailable")
        return row, user

    @classmethod
    async def check_saved_graph(cls, profile_id, graph, catalog):
        """Admit only name-only registered references before native Flow persistence."""
        from langflow.services.deps import session_scope
        from laomedo.integrations.langflow.execution.providers.admission import (
            ProviderGraphAdmission,
        )

        pending = list(graph.get("nodes", []))
        selections = []
        while pending:
            node = pending.pop()
            data = node["data"]
            component = data["node"]
            nested = component.get("flow")
            if nested:
                pending.extend(nested["data"]["nodes"])
            field = (component.get("template") or {}).get("mcp_server")
            if field is None:
                continue
            if not isinstance(field, dict) or field.get("load_from_db"):
                raise McpError("mcp_registration_unavailable")
            value = field.get("value")
            if value in (None, "", {}):
                if catalog.classification(data["type"]) == "MCPTools":
                    ProviderGraphAdmission.check_mcp_parameters(node)
                continue
            if catalog.classification(data["type"]) != "MCPTools":
                raise McpError("mcp_registration_unavailable")
            selections.append(
                ProviderGraphAdmission.mcp_selection(node, {}, (), require_target=False)
            )
        if not selections:
            return
        profile_id = UUID(str(profile_id))
        async with session_scope() as session:
            for selection in selections:
                await cls.registered_row(session, profile_id, selection)

    async def _row(self, selection, *, configuration=False):
        """Load an exact enabled owner/version, decrypting only for approved discovery."""
        from langflow.services.deps import session_scope

        self.connections.check_lease(self.plan.lease_hash)
        for node in self.plan.nodes:
            account = self.connections.admitted(
                self.plan.profile_id, node.connection_id, node.generation
            )
            if account.provider != node.provider:
                raise McpError("mcp_registration_unavailable")
        if self.closed or time.monotonic() >= self.plan.deadline:
            raise McpError("mcp_registration_unavailable")
        async with session_scope() as session:
            row, user = await self.registered_row(
                session, self.plan.profile_id, selection
            )
            if not configuration:
                return None
            from langflow.api.v2.mcp import ensure_mcp_stdio_access
            from langflow.services.auth.mcp_encryption import decrypt_mcp_config
            from langflow.services.deps import (
                get_settings_service,
                get_variable_service,
            )
            from lfx.base.mcp.util import config_uses_global_variables

            config = decrypt_mcp_config(row.config or {})
            ensure_mcp_stdio_access(config, user, get_settings_service().settings)
            variables = None
            if config_uses_global_variables(config):
                variables = await get_variable_service().get_all_decrypted_variables(
                    user_id=self.plan.profile_id, session=session
                )
            return config, variables

    async def check(self, selection=None):
        """Recheck metadata and lease without opening connections or decrypting secrets."""
        for item in (selection,) if selection is not None else self.selections:
            await self._row(item)

    async def prepare(self):
        """Discover pinned registrations and attach host-only per-Agent manifests."""
        from lfx.base.mcp.util import (
            MCPStdioClient,
            MCPStreamableHttpClient,
            update_tools,
        )

        if not self.selections:
            return self.plan
        self.registry = McpRegistry.current()
        await self.check()
        tools = {}
        for selection in self.selections:
            config, variables = await self._row(selection, configuration=True)
            stdio = MCPStdioClient(tool_execution_timeout=CALL_TIMEOUT_SECONDS)
            http = MCPStreamableHttpClient(tool_execution_timeout=CALL_TIMEOUT_SECONDS)
            # No shared component cache: these managers belong only to this job.
            for client in (stdio, http):
                client.set_session_context(
                    f"{self.plan.profile_id}:{id(self)}:{selection.vertex_id}"
                )
                self.clients.append(client)
            try:
                _, discovered, _ = await asyncio.wait_for(
                    update_tools(
                        server_name=selection.name,
                        server_config=config,
                        mcp_stdio_client=stdio,
                        mcp_streamable_http_client=http,
                        request_variables=variables,
                        url_variables=variables,
                        current_user_id=self.plan.profile_id,
                    ),
                    timeout=min(
                        CALL_TIMEOUT_SECONDS,
                        max(0, self.plan.deadline - time.monotonic()),
                    ),
                )
            except Exception:
                raise McpError("mcp_connection_unavailable") from None
            await self.check(selection)
            tools[selection.vertex_id] = [
                RegisteredMcpTool(self, selection, tool) for tool in discovered
            ]
        nodes = []
        for node in self.plan.nodes:
            selected = [
                tool
                for selection in self.selections
                if node.vertex_id in selection.targets
                for tool in tools[selection.vertex_id]
            ]
            if any(node.vertex_id in item.targets for item in self.selections):
                if node.review_source is not None or node.policy is None:
                    raise McpError("mcp_tool_approval_unsupported")
                registration = await self.registry.register(selected)
                self.registrations.append(registration.registration_id)
                if self.maintenance is None:
                    self.maintenance = asyncio.create_task(
                        self._maintain_registrations()
                    )
                node = node.model_copy(
                    update={
                        "policy": node.policy.model_copy(
                            update={"mcp_registration": registration}
                        )
                    }
                )
            nodes.append(node)
        await self.check()
        return self.plan.model_copy(update={"nodes": tuple(nodes)})

    async def _maintain_registrations(self):
        """Fence and renew only queued grants while native claims own their heartbeat."""
        try:
            while not self.closed:
                await asyncio.sleep(self.registry.settings.lease_seconds / 3)
                await self.check()
                for identifier in tuple(self.registrations):
                    self.registry.renew_unclaimed(identifier)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Withhold calls/results immediately; retain any failed revocation
            # receipts for the ordinary job owner's cleanup/reconciliation.
            self.closed = True
            for identifier in tuple(self.registrations):
                try:
                    self.registry.release(identifier)
                    self.registrations.remove(identifier)
                except Exception:
                    continue

    async def close(self):
        """Revoke grants first; retain failed owned-client cleanup for reconciliation."""
        self.closed = True
        failed = False
        if self.maintenance is not None:
            self.maintenance.cancel()
            try:
                await self.maintenance
            except asyncio.CancelledError:
                pass
            self.maintenance = None
        if self.registry is not None:
            for identifier in tuple(self.registrations):
                try:
                    self.registry.release(identifier)
                    self.registrations.remove(identifier)
                except Exception:
                    failed = True
        for client in tuple(self.clients):
            try:
                await asyncio.wait_for(self._close_client(client), CALL_TIMEOUT_SECONDS)
                self.clients.remove(client)
            except Exception:
                failed = True
        if failed:
            raise McpError("mcp_connection_unavailable")

    async def _close_client(self, client):
        """Drain only the private per-job native manager, never a shared pool."""
        try:
            await client.disconnect()
        finally:
            # Native disconnect may lazily create the manager even for an
            # unused transport. Capture it afterwards so its reaper cannot leak.
            manager = getattr(client, "_session_manager", None)
            if manager is not None:
                await manager.cleanup_all()
