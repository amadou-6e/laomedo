"""Authenticated, turn-scoped Claude Code OTLP capture (content is not retained)."""

from __future__ import annotations
from laomedo.agents.agents.claude.activity.models import ClaudeTelemetryEnvironment

from .http.server import ClaudeTelemetryHttpServer
import json
from laomedo.agents.agents.claude.activity.settings import EVENTS
from laomedo.agents.agents.claude.activity.utils import safe_attributes
import re
import secrets
import threading


class ClaudeTelemetry:
    def bind_thread(self, thread_id):
        """Bind the observed ACP native identity before submitting a model prompt.

        ACP assigns fresh native session IDs during session/new. Replacing the
        provisional host identity before dispatch keeps subsequent exports scoped
        to the same native conversation as retained SDK events.
        """
        with self.lock:
            self.scope = {**self.scope, "thread_id": thread_id}

    def __init__(self, directory, *, run_id, thread_id, turn_id):
        from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
            ExportLogsServiceRequest,
        )
        from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
            ExportTraceServiceRequest,
        )
        from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
            ExportMetricsServiceRequest,
        )

        self.scope = {"run_id": run_id, "thread_id": thread_id, "turn_id": turn_id}
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.count = 0
        self.failed = False
        self.output = (directory / "otel-events.jsonl").open("a", encoding="utf-8")
        types = {
            "/v1/logs": ExportLogsServiceRequest,
            "/v1/traces": ExportTraceServiceRequest,
            "/v1/metrics": ExportMetricsServiceRequest,
        }

        try:
            self.server = ClaudeTelemetryHttpServer(
                self, ("127.0.0.1", 0), request_types=types
            )
            self.server.daemon_threads = (
                False  # server_close joins bounded upload handlers.
            )
            endpoint = "http://host.docker.internal:" + str(self.server.server_port)
            settings = ClaudeTelemetryEnvironment(
                endpoint=endpoint, token=self.token
            ).to_environment()
            self.environment = settings
            self.thread = threading.Thread(
                target=self.server.serve_forever, daemon=True
            )
            self.thread.start()
        except Exception:
            if hasattr(self, "server"):
                self.server.server_close()
            self.output.close()
            raise

    def record(self, attributes, **value):
        native = attributes.get("session.id")
        conflict = isinstance(native, str) and native != self.scope["thread_id"]
        calls = {
            attributes[key]
            for key in ("call.id", "tool_use_id", "gen_ai.tool.call.id")
            if isinstance(attributes.get(key), str) and attributes[key]
        }
        if len(calls) == 1:
            attributes = {**attributes, "call.id": next(iter(calls))}
        elif len(calls) > 1:
            conflict = True
        # Scope is attested by the capability-bound receiver for this controller
        # process, never guessed from timestamps or resource labels.
        attributes = {
            **attributes,
            "conversation.id": self.scope["thread_id"],
            "turn.id": self.scope["turn_id"],
        }
        return {
            "provenance": "claude-code-otlp",
            "capture_scope": self.scope,
            "attributes": attributes,
            **({"scope_conflict": True} if conflict else {}),
            **value,
        }

    def decode(self, message, path):
        result = []
        size = 0

        def append(value):
            nonlocal size
            size += len(json.dumps(value, allow_nan=False).encode("utf-8"))
            if len(result) >= 4096 or size > 8 * 1024 * 1024:
                raise ValueError("export_capacity_exceeded")
            result.append(value)

        field, scope_field, record_field = {
            "/v1/logs": ("resource_logs", "scope_logs", "log_records"),
            "/v1/traces": ("resource_spans", "scope_spans", "spans"),
            "/v1/metrics": ("resource_metrics", "scope_metrics", "metrics"),
        }[path]
        for resource in getattr(message, field):
            resource_attrs = safe_attributes(resource.resource.attributes)
            for scope in getattr(resource, scope_field):
                for record in getattr(scope, record_field):
                    name = record.name if path != "/v1/logs" else ""
                    if path == "/v1/metrics":
                        if not re.fullmatch(r"claude_code\.[a-z_.]+", name):
                            continue
                        kind = record.WhichOneof("data")
                        if kind not in {"sum", "gauge", "histogram"}:
                            continue
                        data = getattr(record, kind)
                        for point in data.data_points:
                            attrs = {
                                **resource_attrs,
                                **safe_attributes(point.attributes),
                            }
                            sample = (
                                {
                                    "count": str(point.count),
                                    **(
                                        {"sum": point.sum}
                                        if point.HasField("sum")
                                        else {}
                                    ),
                                    "bucket_counts": list(point.bucket_counts),
                                    "explicit_bounds": list(point.explicit_bounds),
                                }
                                if kind == "histogram"
                                else (
                                    {"value": getattr(point, point.WhichOneof("value"))}
                                    if point.WhichOneof("value")
                                    else {}
                                )
                            )
                            append(
                                self.record(
                                    attrs,
                                    signal="metric",
                                    name=name,
                                    metric_type=kind,
                                    timestamp_ns=str(point.time_unix_nano),
                                    unit=record.unit,
                                    **(
                                        {
                                            "aggregation_temporality": data.aggregation_temporality
                                        }
                                        if kind != "gauge"
                                        else {}
                                    ),
                                    **(
                                        {"is_monotonic": data.is_monotonic}
                                        if kind == "sum"
                                        else {}
                                    ),
                                    **sample,
                                )
                            )
                        continue
                    attrs = {
                        **resource_attrs,
                        **safe_attributes(record.attributes),
                    }
                    if path == "/v1/traces":
                        if not re.fullmatch(r"claude_code\.[a-z_.]+", name):
                            continue
                        append(
                            self.record(
                                attrs,
                                signal="span",
                                name=name,
                                trace_id=record.trace_id.hex(),
                                span_id=record.span_id.hex(),
                                parent_span_id=record.parent_span_id.hex(),
                                started_ns=str(record.start_time_unix_nano),
                                ended_ns=str(record.end_time_unix_nano),
                                status=record.status.code,
                            )
                        )
                    else:
                        # Body may contain content. Retain only a known event identifier.
                        event = attrs.get("event.name", "")
                        if (
                            not event
                            and record.body.WhichOneof("value") == "string_value"
                        ):
                            event = record.body.string_value
                        if event.removeprefix("claude_code.") not in EVENTS:
                            event = "claude_code.event"
                        append(
                            self.record(
                                attrs,
                                signal="log",
                                name=event,
                                timestamp_ns=str(record.time_unix_nano),
                                trace_id=record.trace_id.hex(),
                                span_id=record.span_id.hex(),
                            )
                        )
        return result

    def close(self):
        """Join the receiver and bounded uploads before closing the event writer."""
        try:
            self.server.shutdown()
        finally:
            try:
                self.server.server_close()
                self.thread.join(5)
            finally:
                with self.lock:
                    self.output.close()
        if self.thread.is_alive():
            raise RuntimeError("receiver_close_unconfirmed")
