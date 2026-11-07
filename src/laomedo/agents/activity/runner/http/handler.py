"""Module-level request handling preserving the existing local HTTP contract."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from http.server import BaseHTTPRequestHandler
import json
from laomedo.agents.activity.runner.utils import attributes
import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .server import LaunchTelemetryHttpServer


class LaunchTelemetryRequestHandler(BaseHTTPRequestHandler):
    """Handle the existing wire protocol through this server's explicit owner."""

    server: "LaunchTelemetryHttpServer"

    def log_message(self, *args):
        """Suppress default HTTP logging without emitting capability-bearing requests."""
        pass

    def do_POST(self):
        """Authenticate and handle the existing request protocol, preserving wire errors."""
        if not secrets.compare_digest(
            self.headers.get("Authorization", ""), "Bearer " + self.server.owner.token
        ):
            self.send_error(401)
            return
        if self.path not in {"/v1/logs", "/v1/traces"}:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8 * 1024 * 1024:
                self.send_error(413)
                return
            message = self.server.request_types[self.path]()
            message.ParseFromString(self.rfile.read(length))
            records = []
            for resource in (
                message.resource_logs
                if self.path == "/v1/logs"
                else message.resource_spans
            ):
                for scope in (
                    resource.scope_logs
                    if self.path == "/v1/logs"
                    else resource.scope_spans
                ):
                    for record in (
                        scope.log_records if self.path == "/v1/logs" else scope.spans
                    ):
                        value = {
                            "signal": ("log" if self.path == "/v1/logs" else "span"),
                            "provenance": self.server.provenance,
                            "trace_id": record.trace_id.hex(),
                            "span_id": record.span_id.hex(),
                            "attributes": attributes(record.attributes),
                        }
                        if self.path == "/v1/traces":
                            value.update(
                                name=record.name,
                                parent_span_id=record.parent_span_id.hex(),
                                started_ns=str(record.start_time_unix_nano),
                                ended_ns=str(record.end_time_unix_nano),
                                status=record.status.code,
                            )
                        else:
                            value["timestamp_ns"] = str(record.time_unix_nano)
                        records.append(value)
            with self.server.owner.lock:
                for value in records:
                    self.server.owner.output.write(
                        json.dumps(
                            {
                                "received_at": datetime.now(timezone.utc).isoformat(),
                                "event": {
                                    "method": "otel/record",
                                    "params": value,
                                },
                            }
                        )
                        + "\n"
                    )
                self.server.owner.output.flush()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.send_header("Content-Length", "0")
            self.end_headers()
        except Exception:
            self.send_error(400)
