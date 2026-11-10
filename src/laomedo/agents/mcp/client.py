"""Runner-side admission and supervision of host-private forwarding access."""

import json
import threading
import time
from urllib.request import Request, ProxyHandler, build_opener
from uuid import UUID

from laomedo.agents.mcp.errors import McpError
from laomedo.agents.mcp.models import McpConnection, McpManifest
from laomedo.agents.mcp.settings import McpSettings, MAX_REGISTRATION_BYTES
from laomedo.http.redirect import NoRedirect
from laomedo.host.private_state.utils import prepare_private_directory


class McpAccess:
    """Resolve an opaque reference locally; never admit wire-supplied endpoints.

    The bearer capability stays on this private host object. Public records retain
    only the manifest. Native projections explicitly unwrap the scoped capability.
    """

    def __init__(self, identifier, manifest, *, settings=None):
        """Read and verify one fixed-root private admission before provider dispatch."""
        self.settings = settings or McpSettings()
        self.connection = None
        self._closed = False
        self._last_health = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._monitor_thread = None
        self._failure = None
        self.run_id = None
        self._opener = build_opener(ProxyHandler({}), NoRedirect())
        try:
            if str(UUID(identifier)) != identifier:
                raise ValueError()
            path = self.settings.state_directory() / (identifier + ".json")
            if not path.exists():
                raise McpError("mcp_registration_expired")
            if not path.parent.is_dir():
                raise ValueError()
            prepare_private_directory(
                path.parent, policy=self.settings.permission_policy()
            )
            if path.is_symlink() or path.stat().st_size > MAX_REGISTRATION_BYTES:
                raise ValueError()
            connection = McpConnection.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            expected = McpManifest.model_validate(manifest)
            if (
                str(connection.registration.registration_id) != identifier
                or connection.registration.manifest.digest() != expected.digest()
                or connection.bind != self.settings.bind
                or connection.controller_host != self.settings.controller_host
            ):
                raise ValueError()
            self.connection = connection
            self.check_health(force=True)
        except McpError:
            raise
        except Exception:
            raise McpError("mcp_registration_unavailable") from None

    @staticmethod
    def semantic_request(request):
        """Exclude only ephemeral MCP admission from the canonical request hash."""
        body = {
            key: value for key, value in request.items() if key != "mcp_registration"
        }
        if "mcp_manifest" in body:
            body["mcp_manifest"] = McpManifest.model_validate(
                body["mcp_manifest"]
            ).model_dump(mode="json")
        return body

    def _request(self, method, body=None):
        """Make one authenticated local request without proxies, redirects or retry."""
        req = Request(
            self.connection.endpoint(),
            method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={
                "Authorization": "Bearer " + self.connection.token.get_secret_value(),
                "Content-Type": "application/json",
            },
        )
        try:
            with self._opener.open(req, timeout=5) as response:
                result = json.loads(response.read(4096))
            if (
                method == "GET"
                and result.get("manifest_digest")
                != self.connection.registration.manifest.digest()
            ):
                raise ValueError()
            return result
        except Exception:
            raise McpError("mcp_connection_unavailable") from None

    def check_health(self, *, force=False):
        """Read supervisor health without blocking the native ACP cancellation loop."""
        if self._closed:
            raise McpError("mcp_registration_unavailable")
        if self._failure:
            raise McpError(self._failure)
        if force:
            result = self._request("GET")
            self.run_id = result.get("run_id")
            self._last_health = time.monotonic()

    def claim(self, run_id):
        """Bind once to an exact invocation and start an independent heartbeat."""
        if self.run_id is not None and self.run_id != run_id:
            raise McpError("mcp_run_binding_mismatch")
        if self._monitor_thread is not None:
            return
        reply = self._request(
            "POST",
            {
                "jsonrpc": "2.0",
                "id": "claim",
                "method": "_laomedo/claim",
                "params": {"run_id": run_id},
            },
        )
        if reply.get("result", {}).get("run_id") != run_id:
            raise McpError("mcp_run_binding_mismatch")
        self.run_id = run_id
        self._monitor_thread = threading.Thread(target=self._monitor, daemon=True)
        self._monitor_thread.start()

    def _monitor(self):
        """Keep I/O off native loops and stop admission promptly when the app is lost."""
        while not self._stop.wait(1):
            try:
                result = self._request("GET")
                if result.get("run_id") != self.run_id:
                    raise McpError("mcp_run_binding_mismatch")
                self._last_health = time.monotonic()
            except McpError as exc:
                self._failure = exc.code
                return

    def close(self):
        """Revoke future access; an unreachable app never implies no prior effects."""
        with self._lock:
            if not self._closed:
                self._closed = True
                self._stop.set()
                self._request("DELETE")

    def tool_names(self):
        """Return only the exact externally admitted native tool names."""
        return tuple(
            tool.external_name() for tool in self.connection.registration.manifest.tools
        )

    def redact(self, value):
        """Remove this exact scoped capability before retaining native observations."""
        encoded = json.dumps(value)
        return json.loads(
            encoded.replace(self.connection.token.get_secret_value(), "[redacted]")
        )

    def acp_server(self):
        """Project one scoped HTTP MCP server into private ACP session setup."""
        from acp.schema import McpServerHttp, HttpHeader

        return McpServerHttp(
            name="external",
            url=self.connection.endpoint(controller=True),
            headers=[
                HttpHeader(
                    name="Authorization",
                    value="Bearer " + self.connection.token.get_secret_value(),
                )
            ],
        )

    def opencode_config(self):
        """Project only the forwarding capability into private native OpenCode config."""
        return {
            "type": "remote",
            "url": self.connection.endpoint(controller=True),
            "headers": {
                "Authorization": "Bearer " + self.connection.token.get_secret_value()
            },
            "oauth": False,
        }
