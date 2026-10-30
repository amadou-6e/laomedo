"""Module-level request handling preserving the existing local HTTP contract."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from http.server import BaseHTTPRequestHandler
import json
import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .server import ClaudeTelemetryHttpServer


class ClaudeTelemetryRequestHandler(BaseHTTPRequestHandler):
    """Handle the existing wire protocol through this server's explicit owner."""

    server: "ClaudeTelemetryHttpServer"

    def log_message(self, *_):
        """Suppress default HTTP logging without emitting capability-bearing requests."""
        pass

    def setup(self):
        """Initialize request streams and retain the existing bounded upload timeout."""
        super().setup()
        self.connection.settimeout(5)

    def do_POST(self):
        """Authenticate and handle the existing request protocol, preserving wire errors."""
        if not secrets.compare_digest(
            self.headers.get("Authorization", ""), "Bearer " + self.server.owner.token
        ):
            self.send_error(401)
            return
        if self.path not in self.server.request_types:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8 * 1024 * 1024:
                self.server.owner.failed = True
                self.send_error(413)
                return
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("incomplete_export")
            message = self.server.request_types[self.path]()
            message.ParseFromString(raw)
            records = self.server.owner.decode(message, self.path)
            with self.server.owner.lock:
                for value in records:
                    self.server.owner.output.write(
                        json.dumps(
                            {
                                "received_at": datetime.now(
                                    timezone.utc
                                ).isoformat(),
                                "event": {
                                    "method": "otel/record",
                                    "params": value,
                                },
                            },
                            allow_nan=False,
                        )
                        + "\n"
                    )
                self.server.owner.output.flush()
                self.server.owner.count += len(records)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.send_header("Content-Length", "0")
            self.end_headers()
        except Exception:
            self.server.owner.failed = True
            try:
                self.send_error(400)
            except OSError:
                pass
