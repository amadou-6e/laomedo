"""Module-level request handling preserving the existing local HTTP contract."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .server import BrokerHttpServer


class BrokerRequestHandler(BaseHTTPRequestHandler):
    """Handle the existing wire protocol through this server's explicit owner."""

    server: "BrokerHttpServer"

    def log_message(self, *_):
        """Suppress default HTTP logging without emitting capability-bearing requests."""
        pass

    def setup(self):
        """Bound malformed or abandoned broker uploads."""
        super().setup()
        self.connection.settimeout(5)

    def do_POST(self):
        """Authenticate and handle the existing request protocol, preserving wire errors."""
        if (
            self.path != "/mcp"
            or self.headers.get("Authorization") != "Bearer " + self.server.broker.token
        ):
            self.send_error(403)
            return
        msg = None
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                raise ValueError("invalid_body")
            msg = json.loads(self.rfile.read(length))
            if "id" not in msg:
                self.send_response(202)
                self.end_headers()
                return
            value = self.server.broker.rpc(msg.get("method"), msg.get("params", {}))
            body = {"jsonrpc": "2.0", "id": msg["id"], "result": value}
        except Exception:
            body = {
                "jsonrpc": "2.0",
                "id": msg.get("id") if isinstance(msg, dict) else None,
                "error": {"code": -32602, "message": "broker_request_failed"},
            }
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
