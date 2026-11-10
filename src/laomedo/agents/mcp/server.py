"""Bounded authenticated JSON-RPC forwarding for isolated MCP controllers."""

import asyncio
from concurrent.futures import TimeoutError, CancelledError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.parse import urlsplit
from uuid import UUID

from laomedo.agents.mcp.errors import McpError
from laomedo.agents.mcp.settings import CALL_TIMEOUT_SECONDS, MAX_ARGUMENT_BYTES


class McpServer(ThreadingHTTPServer):
    """Bound request threads before authentication and never expose server diagnostics."""

    daemon_threads = True
    block_on_close = False

    def __init__(self, address, registry):
        """Bind the explicitly admitted interface and retain its app-loop owner."""
        self.registry = registry
        self.capacity = threading.BoundedSemaphore(registry.settings.max_calls + 8)
        super().__init__(address, McpRequestHandler)

    def process_request(self, request, client_address):
        """Reject excess sockets instead of creating unbounded worker threads."""
        if not self.capacity.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.capacity.release()
            raise

    def process_request_thread(self, request, client_address):
        """Return the admission slot even when parsing or forwarding fails."""
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.capacity.release()

    def handle_error(self, request, client_address):
        """Suppress raw exception logging because forwarded data can be sensitive."""
        return None


class McpRequestHandler(BaseHTTPRequestHandler):
    """Translate a stateless MCP HTTP exchange without inspecting upstream config."""

    def setup(self):
        """Limit header/body socket waits before any grant or native call exists."""
        self.request.settimeout(5)
        super().setup()

    def log_message(self, *args):
        """Do not log capabilities, request arguments or results."""
        return None

    def do_GET(self):
        """Authenticated runner supervision; does not discover or execute tools."""
        if "text/event-stream" in self.headers.get("Accept", ""):
            self._reply(405, None)
            return
        self._forward("GET")

    def do_DELETE(self):
        """Revoke this exact invocation capability."""
        self._forward("DELETE")

    def do_POST(self):
        """Forward one bounded MCP message to the owning application loop."""
        self._forward("POST")

    def _forward(self, method):
        """Perform path/token validation and bounded app-loop dispatch."""
        future = None
        body = None
        try:
            parsed = urlsplit(self.path)
            parts = parsed.path.split("/")
            if len(parts) != 3 or parts[2] != "mcp" or parsed.query or parsed.fragment:
                raise McpError("mcp_registration_unavailable")
            identifier = str(UUID(parts[1]))
            if identifier != parts[1]:
                raise McpError("mcp_registration_unavailable")
            authorization = self.headers.get("Authorization", "")
            if not authorization.startswith("Bearer "):
                raise McpError("mcp_registration_unavailable")
            token = authorization[7:]
            registry = self.server.registry
            # Authenticate before reading a body or allocating a native task.
            future = asyncio.run_coroutine_threadsafe(
                registry.request(identifier, token, "GET"), registry.loop
            )
            health = future.result(timeout=5)
            if method == "GET":
                self._reply(200, health)
                return
            if method == "POST":
                length = int(self.headers.get("Content-Length", "0"))
                if (
                    self.headers.get("Transfer-Encoding")
                    or not 1 <= length <= MAX_ARGUMENT_BYTES
                ):
                    raise McpError("mcp_request_too_large")
                if (
                    self.headers.get("Content-Type", "").split(";")[0]
                    != "application/json"
                ):
                    raise McpError("mcp_protocol_invalid")
                body = json.loads(self.rfile.read(length))
            future = asyncio.run_coroutine_threadsafe(
                registry.request(identifier, token, method, body), registry.loop
            )
            result = future.result(timeout=CALL_TIMEOUT_SECONDS + 10)
            if method == "DELETE":
                self._reply(200, result)
            elif isinstance(body, dict) and "id" in body:
                self._reply(200, {"jsonrpc": "2.0", "id": body["id"], "result": result})
            else:
                self._reply(202, None)
        except (TimeoutError, CancelledError):
            if future:
                future.cancel()
            self._error(body, "mcp_call_outcome_unknown")
        except McpError as exc:
            self._error(body, exc.code)
        except Exception:
            self._error(body, "mcp_connection_unavailable")

    def _error(self, body, code):
        """Return only safe categories, preserving JSON-RPC correlation if available."""
        if isinstance(body, dict) and "id" in body:
            self._reply(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "error": {"code": -32000, "message": code},
                },
            )
        else:
            self._reply(403, {"code": code})

    def _reply(self, status, value):
        """Serialize bounded protocol content without logging it."""
        payload = b"" if value is None else json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)
