"""Exact existing lease and mediation request protocol at module scope."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
from typing import TYPE_CHECKING

from laomedo.host.mediation.errors import MediationError

if TYPE_CHECKING:
    from laomedo.host.leases.server import LeaseHTTPServer


class LeaseRequestHandler(BaseHTTPRequestHandler):
    """Use server-owned dependencies while preserving existing dispatch order."""

    server: LeaseHTTPServer

    def log_message(self, *_):
        """Suppress the framework's access log, including request information."""
        return None

    def do_GET(self):
        """Return existing mediator readiness, otherwise the same not-found reply."""
        if (
            self.path == "/v1/health"
            and self.server.mediator is not None
            and self.server.transport is not None
            and self.server.instance is not None
        ):
            return self._json_reply(
                200, {"status": "ready", "instance": self.server.instance}
            )
        return self._json_reply(404, {"error": "not_found"})

    def do_POST(self):
        """Preserve mediation admission and its precedence over lease-write checks."""
        if self.path == "/v1/mediate":
            if self.server.mediator is None or self.server.transport is None:
                return self._json_reply(503, {"error": "mediator_unavailable"})
            if (
                self.server.instance is not None
                and self.headers.get("X-Laomedo-Mediator-Instance")
                != self.server.instance
            ):
                return self._json_reply(403, {"error": "mediator_instance_mismatch"})
            try:
                size = int(self.headers.get("Content-Length", ""))
                if not 0 < size <= 1024 * 1024 or not self.headers.get(
                    "Authorization", ""
                ).startswith("Bearer "):
                    raise MediationError("request_invalid")
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise MediationError("request_invalid")
                result = self.server.mediator.invoke(
                    token=self.headers["Authorization"][len("Bearer ") :],
                    repository=body.get("repository"),
                    operation=body.get("operation"),
                    payload=body.get("payload"),
                    effect_id=body.get("effect_id"),
                    transport=self.server.transport,
                )
            except (MediationError, ValueError, TypeError) as error:
                code = (
                    error.code
                    if isinstance(error, MediationError)
                    else "request_invalid"
                )
                return self._json_reply(403, {"error": code})
            return self._json_reply(200, result)
        supplied = self.headers.get("Authorization", "")
        accepted = False
        if (
            self.server.mediator is None
            and self.path == "/write"
            and supplied.startswith("Bearer ")
        ):
            accepted, _ = self.server.book.check(supplied[len("Bearer ") :])
        return self._json_reply(200 if accepted else 403, {"accepted": accepted})

    def _json_reply(self, status: int, value: dict):
        """Emit exactly the existing default JSON encoding and response headers."""
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
