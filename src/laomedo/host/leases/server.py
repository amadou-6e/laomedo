"""Loopback lease and mediation HTTP server."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import laomedo.host.leases.grants as _leases_grants
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import json
import laomedo.host.leases.constants as _leases_constants
import laomedo.host.leases.models as _leases_models
import laomedo.host.mediation.errors as _mediation_errors
import laomedo.host.mediation.store as _mediation_store
import os
import queue
import secrets
import subprocess
import sys
import threading
import time

from http.server import ThreadingHTTPServer


class LeaseHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        book: _leases_grants.GrantBook | None,
        mediator: _mediation_store.MediationStore | None = None,
        transport=None,
        instance: str | None = None,
        *,
        host="127.0.0.1",
        port=0,
    ):
        import laomedo.host.leases.grants as _leases_grants

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                if (
                    self.path == "/v1/health"
                    and mediator is not None
                    and transport is not None
                    and instance is not None
                ):
                    return self._json_reply(
                        200, {"status": "ready", "instance": instance}
                    )
                return self._json_reply(404, {"error": "not_found"})

            def do_POST(self):
                if self.path == "/v1/mediate":
                    if mediator is None or transport is None:
                        return self._json_reply(503, {"error": "mediator_unavailable"})
                    if (
                        instance is not None
                        and self.headers.get("X-Laomedo-Mediator-Instance") != instance
                    ):
                        return self._json_reply(
                            403, {"error": "mediator_instance_mismatch"}
                        )
                    try:
                        size = int(self.headers.get("Content-Length", ""))
                        if not 0 < size <= 1024 * 1024 or not self.headers.get(
                            "Authorization", ""
                        ).startswith("Bearer "):
                            raise _mediation_errors.MediationError("request_invalid")
                        body = json.loads(self.rfile.read(size))
                        if not isinstance(body, dict):
                            raise _mediation_errors.MediationError("request_invalid")
                        result = mediator.invoke(
                            token=self.headers["Authorization"][len("Bearer ") :],
                            repository=body.get("repository"),
                            operation=body.get("operation"),
                            payload=body.get("payload"),
                            effect_id=body.get("effect_id"),
                            transport=transport,
                        )
                    except (
                        _mediation_errors.MediationError,
                        ValueError,
                        TypeError,
                    ) as error:
                        code = (
                            error.code
                            if isinstance(error, _mediation_errors.MediationError)
                            else "request_invalid"
                        )
                        return self._json_reply(403, {"error": code})
                    return self._json_reply(200, result)
                supplied = self.headers.get("Authorization", "")
                accepted = False
                if (
                    mediator is None
                    and self.path == "/write"
                    and supplied.startswith("Bearer ")
                ):
                    accepted, _ = book.check(supplied[len("Bearer ") :])
                return self._json_reply(
                    200 if accepted else 403, {"accepted": accepted}
                )

            def _json_reply(self, status: int, value: dict):
                body = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        super().__init__((host, port), Handler)
