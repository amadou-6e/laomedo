"""Module-level request handling preserving the existing local HTTP contract."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .server import CommandHttpServer


class CommandRequestHandler(BaseHTTPRequestHandler):
    """Handle the existing wire protocol through this server's explicit owner."""

    server: "CommandHttpServer"

    def log_message(self, *_):
        """Suppress default HTTP logging without emitting capability-bearing requests."""
        pass

    def do_POST(self):
        """Authenticate and handle the existing request protocol, preserving wire errors."""
        if self.path != "/command" or not secrets.compare_digest(
            self.headers.get("Authorization", ""), "Bearer " + self.server.owner.token
        ):
            self.send_error(403)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 65536:
                raise ValueError()
            value = json.loads(self.rfile.read(size))
            answer = (
                self.server.owner.mediate(value["github"])
                if isinstance(value, dict) and set(value) == {"github"}
                else self.server.owner.execute(value)
            )
            raw = json.dumps(answer).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except Exception:
            self.send_error(503, "Workspace command unavailable")
