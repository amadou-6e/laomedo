"""Local OTLP receiver bound to one runner launch, with an attribute allowlist."""

from __future__ import annotations

from .http.server import LaunchTelemetryHttpServer
import secrets
import threading


class LaunchTelemetry:
    def __init__(self, directory, *, provenance="runtime-reported"):
        from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
            ExportLogsServiceRequest,
        )
        from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
            ExportTraceServiceRequest,
        )

        token = secrets.token_urlsafe(32)
        self.token = token
        self.output = (directory / "otel-events.jsonl").open("a", encoding="utf-8")
        self.lock = threading.Lock()

        self.server = LaunchTelemetryHttpServer(
            self,
            ("127.0.0.1", 0),
            provenance=provenance,
            request_types={
                "/v1/logs": ExportLogsServiceRequest,
                "/v1/traces": ExportTraceServiceRequest,
            },
        )
        self.server.daemon_threads = True
        self.server.timeout = 10
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def arguments(self):
        base = "http://host.docker.internal:" + str(self.server.server_port)

        def exporter(signal):
            return (
                '{otlp-http={endpoint="'
                + base
                + "/v1/"
                + signal
                + '",protocol="binary",headers={Authorization="Bearer '
                + self.token
                + '"}}}'
            )

        return [
            "-c",
            "otel.exporter=" + exporter("logs"),
            "-c",
            "otel.trace_exporter=" + exporter("traces"),
            "-c",
            "otel.log_user_prompt=false",
        ]

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        with self.lock:
            self.output.close()
