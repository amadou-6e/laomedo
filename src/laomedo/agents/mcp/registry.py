"""App-lifetime ownership of graph-selected native tools and private grants."""

import asyncio
from contextlib import asynccontextmanager, suppress
import secrets
import threading
import time
from typing import ClassVar
from uuid import uuid4, UUID

from laomedo.agents.agents.base.utils import _json
from laomedo.agents.mcp.errors import McpError
from laomedo.agents.mcp.models import (
    McpConnection,
    McpLease,
    McpManifest,
    McpRegistration,
)
from laomedo.agents.mcp.settings import McpSettings
from laomedo.host.private_state.utils import prepare_private_directory


class McpRegistry:
    """Retain borrowed tools on the original app loop beyond a graph build.

    Only the installed app lifespan may activate registration. Upstream clients
    remain owned by Langflow; release removes references and grants, not sessions.
    """

    _active: ClassVar["McpRegistry | None"] = None

    def __init__(self, settings: McpSettings, upstream=None):
        """Prepare an inactive owner; do not start threads or load credentials."""
        self.settings = settings
        self.upstream = upstream
        self.loop = None
        self.server = None
        self.thread = None
        self.leases = {}
        self.calls = None
        self.directory = None
        self.registration_lock = None

    @classmethod
    def install(cls, app, settings: McpSettings):
        """Compose with the upstream ASGI lifespan, preserving its teardown."""
        registry = cls(settings, app.router.lifespan_context)
        app.router.lifespan_context = registry.lifespan
        app.state.laomedo_mcp = registry
        return registry

    @classmethod
    def current(cls):
        """Refuse headless or foreign-loop registrations rather than borrowing unsafely."""
        owner = cls._active
        if owner is None or owner.loop is not asyncio.get_running_loop():
            raise McpError("mcp_app_lifetime_required")
        return owner

    @asynccontextmanager
    async def lifespan(self, app):
        """Activate after upstream startup and revoke before upstream shutdown."""
        async with self.upstream(app) as state:
            if type(self)._active is not None:
                raise McpError("mcp_app_owner_conflict")
            self.loop = asyncio.get_running_loop()
            self.calls = asyncio.Semaphore(self.settings.max_calls)
            self.registration_lock = asyncio.Lock()
            type(self)._active = self
            reaper = asyncio.create_task(self._expire())
            try:
                yield state
            finally:
                type(self)._active = None
                reaper.cancel()
                with suppress(asyncio.CancelledError):
                    await reaper
                for registration_id in list(self.leases):
                    self.release(registration_id)
                if self.server:
                    await asyncio.to_thread(self.server.shutdown)
                    self.server.server_close()
                    await asyncio.to_thread(self.thread.join, 5)
                self.loop = None

    async def register(self, tools) -> McpRegistration:
        """Serialize registration while allowing app requests during private I/O."""
        if self.current() is not self:
            raise McpError("mcp_app_lifetime_required")
        async with self.registration_lock:
            return await self._register(tools)

    def release(self, registration_id):
        """Revoke future calls and discard only this registration's private file."""
        identifier = str(UUID(str(registration_id)))
        lease = self.leases.pop(identifier, None)
        if lease:
            for task in list(lease.tasks.values()):
                task.cancel()
        if self.directory:
            (self.directory / (identifier + ".json")).unlink(missing_ok=True)

    def release_unclaimed(self, registration_id):
        """Discard refused/replayed admission without revoking an active attempt."""
        identifier = str(UUID(str(registration_id)))
        lease = self.leases.get(identifier)
        if lease is not None and lease.run_id is None:
            self.release(identifier)

    async def request(self, identifier, token, method, body=None):
        """Authorize one request before discovery or invocation; never widen a grant."""
        lease = self.leases.get(identifier)
        if (
            lease is None
            or lease.expires <= time.monotonic()
            or not secrets.compare_digest(
                lease.connection.token.get_secret_value(), token
            )
        ):
            raise McpError("mcp_registration_unavailable")
        if method == "DELETE":
            self.release(identifier)
            return {}
        lease.expires = time.monotonic() + self.settings.lease_seconds
        if method == "GET":
            return {
                "manifest_digest": lease.connection.registration.manifest.digest(),
                "run_id": str(lease.run_id) if lease.run_id else None,
            }
        if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
            raise McpError("mcp_protocol_invalid")
        operation = body.get("method")
        if operation == "_laomedo/claim":
            try:
                run_id = UUID(body["params"]["run_id"])
            except Exception:
                raise McpError("mcp_protocol_invalid") from None
            if lease.run_id is not None and lease.run_id != run_id:
                raise McpError("mcp_run_binding_mismatch")
            lease.run_id = run_id
            return {"run_id": str(run_id)}
        if lease.run_id is None:
            raise McpError("mcp_registration_unclaimed")
        if operation == "initialize":
            return {
                "protocolVersion": body.get("params", {}).get(
                    "protocolVersion", "2024-11-05"
                ),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "laomedo-external", "version": "1"},
            }
        if operation == "notifications/cancelled":
            task = lease.tasks.get(body.get("params", {}).get("requestId"))
            if task:
                task.cancel()
            return {}
        if operation in {"notifications/initialized", "ping"}:
            return {}
        if operation == "tools/list":
            return {
                "tools": [
                    {
                        "name": name,
                        "description": tool.descriptor.description,
                        "inputSchema": tool.descriptor.input_schema,
                    }
                    for name, tool in lease.tools.items()
                ]
            }
        if operation != "tools/call":
            raise McpError("mcp_method_unsupported")
        params = body.get("params")
        if not isinstance(params, dict) or params.get("name") not in lease.tools:
            raise McpError("mcp_tool_not_selected")
        if self.calls.locked():
            raise McpError("mcp_call_limit")
        request_id = body.get("id")
        if type(request_id) not in (str, int) or request_id in lease.tasks:
            raise McpError("mcp_protocol_invalid")
        async with self.calls:
            lease.tasks[request_id] = asyncio.current_task()
            try:
                return await lease.tools[params["name"]].invoke(
                    params.get("arguments", {})
                )
            finally:
                lease.tasks.pop(request_id, None)

    def _prepare_directory(self):
        """Verify directory custody on a worker, including Windows subprocesses."""
        prepare_private_directory(
            self.directory, policy=self.settings.permission_policy()
        )

    async def _register(self, tools) -> McpRegistration:
        """Publish an exact bounded manifest and a host-private random capability."""
        from laomedo.agents.mcp.server import McpServer

        if self.current() is not self:
            raise McpError("mcp_app_lifetime_required")
        if len(self.leases) >= self.settings.max_registrations:
            raise McpError("mcp_registration_limit")
        if not tools or len(tools) > 128:
            raise McpError("mcp_tool_limit")
        admitted = {}
        for tool in tools:
            name = tool.descriptor.external_name()
            if name in admitted:
                raise McpError("mcp_duplicate_tool")
            admitted[name] = tool
        if len({tool.descriptor.server for tool in tools}) > 32:
            raise McpError("mcp_server_limit")
        if self.server is None:
            self.directory = self.settings.state_directory()
            try:
                await asyncio.to_thread(self._prepare_directory)
            except Exception:
                raise McpError("mcp_private_state_unverified") from None
            self.server = McpServer((self.settings.bind, 0), self)
            self.thread = threading.Thread(
                target=self.server.serve_forever, daemon=True
            )
            self.thread.start()
        registration = McpRegistration(
            registration_id=uuid4(),
            manifest=McpManifest(tools=tuple(tool.descriptor for tool in tools)),
        )
        connection = McpConnection(
            registration=registration,
            port=self.server.server_port,
            bind=self.settings.bind,
            controller_host=self.settings.controller_host,
            token=secrets.token_urlsafe(32),
        )
        identifier = str(registration.registration_id)
        self.leases[identifier] = McpLease(
            connection=connection,
            tools=admitted,
            expires=time.monotonic() + self.settings.lease_seconds,
        )
        path = self.directory / (identifier + ".json")
        write = asyncio.create_task(
            asyncio.to_thread(_json, path, connection.private_payload())
        )
        try:
            await asyncio.shield(write)
        except asyncio.CancelledError:
            self.leases.pop(identifier, None)
            # A worker cannot be cancelled: wait for its private write before unlinking.
            with suppress(Exception):
                await write
            await asyncio.to_thread(path.unlink, missing_ok=True)
            raise
        except Exception:
            self.leases.pop(identifier, None)
            await asyncio.to_thread(path.unlink, missing_ok=True)
            raise McpError("mcp_registration_failed") from None
        return registration

    async def _expire(self):
        """Reclaim abandoned app registrations without imposing a run duration cap."""
        while True:
            await asyncio.sleep(5)
            for identifier, lease in list(self.leases.items()):
                if lease.expires <= time.monotonic():
                    self.release(identifier)
