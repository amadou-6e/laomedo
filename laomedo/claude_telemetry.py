"""Authenticated, turn-scoped Claude Code OTLP capture (content is not retained)."""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import secrets
import threading
from uuid import uuid4

from .runner_telemetry import ALLOWED

SAFE = ALLOWED | frozenset({'session.id', 'event.sequence', 'input_tokens', 'output_tokens',
    'cache_read_tokens', 'cache_creation_tokens', 'cost_usd', 'duration_ms', 'success',
    'status_code', 'error.type', 'error_category', 'type', 'tool_name', 'tool_use_id',
    'interaction.sequence', 'api_request_id', 'service.name', 'service.version',
    'span.type', 'gen_ai.system', 'tool_name_safe', 'error_class', 'effort', 'request_id',
    'client_request_id', 'gen_ai.response.id', 'attempt', 'ttft_ms', 'first_content_ms',
    'interaction.duration_ms', 'result_tokens', 'gen_ai.tool.call.id'})


EVENTS = frozenset({'user_prompt', 'assistant_response', 'tool_result', 'api_request', 'api_error',
    'api_refusal', 'tool_decision', 'permission_mode_changed', 'auth', 'mcp_server_connection',
    'internal_error', 'plugin_installed', 'plugin_loaded', 'skill_activated', 'at_mention',
    'api_retries_exhausted', 'hook_registered', 'hook_execution_start', 'hook_execution_complete',
    'hook_plugin_metrics', 'compaction', 'subagent_completed', 'feedback_survey',
    'retention_sweep', 'managed_settings_resolved', 'safety'})


def safe_attributes(values):
    result = {}
    for pair in values:
        if pair.key not in SAFE:
            continue
        kind = pair.value.WhichOneof('value')
        if kind in {'string_value', 'int_value', 'double_value', 'bool_value'}:
            value = getattr(pair.value, kind)
            if not isinstance(value, str) or len(value) <= 1024:
                result[pair.key] = value
    return result


class ClaudeTelemetry:
    def __init__(self, directory, *, run_id, thread_id, turn_id):
        from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
        from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
        from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
        self.scope = {'run_id': run_id, 'thread_id': thread_id, 'turn_id': turn_id}
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.count = 0
        self.failed = False
        self.output = (directory / 'otel-events.jsonl').open('a', encoding='utf-8')
        self.environment = directory / ('telemetry-environment-' + uuid4().hex)
        owner = self
        types = {'/v1/logs': ExportLogsServiceRequest, '/v1/traces': ExportTraceServiceRequest,
                 '/v1/metrics': ExportMetricsServiceRequest}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def setup(self):
                super().setup()
                self.connection.settimeout(5)

            def do_POST(self):
                if not secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + owner.token):
                    self.send_error(401); return
                if self.path not in types:
                    self.send_error(404); return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 8 * 1024 * 1024:
                        self.send_error(413); return
                    raw = self.rfile.read(length)
                    if len(raw) != length:
                        raise ValueError('incomplete_export')
                    message = types[self.path]()
                    message.ParseFromString(raw)
                    records = owner.decode(message, self.path)
                    with owner.lock:
                        for value in records:
                            owner.output.write(json.dumps({'received_at': datetime.now(timezone.utc).isoformat(),
                                'event': {'method': 'otel/record', 'params': value}}, allow_nan=False) + '\n')
                        owner.output.flush()
                        owner.count += len(records)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/x-protobuf')
                    self.send_header('Content-Length', '0'); self.end_headers()
                except Exception:
                    owner.failed = True
                    try:
                        self.send_error(400)
                    except OSError:
                        pass
        try:
            self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            self.server.daemon_threads = False  # server_close joins bounded upload handlers.
            endpoint = 'http://host.docker.internal:' + str(self.server.server_port)
            settings = {'CLAUDE_CODE_ENABLE_TELEMETRY': '1', 'CLAUDE_CODE_ENHANCED_TELEMETRY_BETA': '1',
                'OTEL_EXPORTER_OTLP_PROTOCOL': 'http/protobuf', 'OTEL_EXPORTER_OTLP_ENDPOINT': endpoint,
                'OTEL_EXPORTER_OTLP_HEADERS': 'Authorization=Bearer ' + self.token,
                'OTEL_METRICS_EXPORTER': 'otlp', 'OTEL_LOGS_EXPORTER': 'otlp', 'OTEL_TRACES_EXPORTER': 'otlp',
                'OTEL_METRIC_EXPORT_INTERVAL': '1000', 'OTEL_LOGS_EXPORT_INTERVAL': '1000',
                'OTEL_TRACES_EXPORT_INTERVAL': '1000', 'OTEL_LOG_USER_PROMPTS': '0',
                'OTEL_LOG_ASSISTANT_RESPONSES': '0', 'OTEL_LOG_TOOL_DETAILS': '0', 'OTEL_LOG_TOOL_CONTENT': '0',
                'OTEL_METRICS_INCLUDE_ACCOUNT_UUID': 'false'}
            self.environment.write_text(''.join(key + '=' + value + '\n' for key, value in settings.items()), encoding='utf-8')
            self.environment.chmod(0o600)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
        except Exception:
            if hasattr(self, 'server'): self.server.server_close()
            self.output.close()
            self.environment.unlink(missing_ok=True)
            raise

    def record(self, attributes, **value):
        native = attributes.get('session.id')
        conflict = isinstance(native, str) and native != self.scope['thread_id']
        calls = {attributes[key] for key in ('call.id', 'tool_use_id', 'gen_ai.tool.call.id')
                 if isinstance(attributes.get(key), str) and attributes[key]}
        if len(calls) == 1:
            attributes = {**attributes, 'call.id': next(iter(calls))}
        elif len(calls) > 1:
            conflict = True
        # Scope is attested by the capability-bound receiver for this controller
        # process, never guessed from timestamps or resource labels.
        attributes = {**attributes, 'conversation.id': self.scope['thread_id'], 'turn.id': self.scope['turn_id']}
        return {'provenance': 'claude-code-otlp', 'capture_scope': self.scope,
                'attributes': attributes, **({'scope_conflict': True} if conflict else {}), **value}

    def decode(self, message, path):
        result = []
        size = 0
        def append(value):
            nonlocal size
            size += len(json.dumps(value, allow_nan=False).encode('utf-8'))
            if len(result) >= 4096 or size > 8 * 1024 * 1024:
                raise ValueError('export_capacity_exceeded')
            result.append(value)
        field, scope_field, record_field = {'/v1/logs': ('resource_logs', 'scope_logs', 'log_records'),
            '/v1/traces': ('resource_spans', 'scope_spans', 'spans'),
            '/v1/metrics': ('resource_metrics', 'scope_metrics', 'metrics')}[path]
        for resource in getattr(message, field):
            resource_attrs = safe_attributes(resource.resource.attributes)
            for scope in getattr(resource, scope_field):
                for record in getattr(scope, record_field):
                    name = record.name if path != '/v1/logs' else ''
                    if path == '/v1/metrics':
                        if not re.fullmatch(r'claude_code\.[a-z_.]+', name): continue
                        kind = record.WhichOneof('data')
                        if kind not in {'sum', 'gauge', 'histogram'}: continue
                        data = getattr(record, kind)
                        for point in data.data_points:
                            attrs = {**resource_attrs, **safe_attributes(point.attributes)}
                            sample = {'count': str(point.count), **({'sum': point.sum} if point.HasField('sum') else {}),
                                'bucket_counts': list(point.bucket_counts), 'explicit_bounds': list(point.explicit_bounds)} if kind == 'histogram' else {'value': getattr(point, point.WhichOneof('value'))} if point.WhichOneof('value') else {}
                            append(self.record(attrs, signal='metric', name=name, metric_type=kind,
                                timestamp_ns=str(point.time_unix_nano), unit=record.unit,
                                **({'aggregation_temporality': data.aggregation_temporality} if kind != 'gauge' else {}),
                                **({'is_monotonic': data.is_monotonic} if kind == 'sum' else {}), **sample))
                        continue
                    attrs = {**resource_attrs, **safe_attributes(record.attributes)}
                    if path == '/v1/traces':
                        if not re.fullmatch(r'claude_code\.[a-z_.]+', name): continue
                        append(self.record(attrs, signal='span', name=name, trace_id=record.trace_id.hex(),
                            span_id=record.span_id.hex(), parent_span_id=record.parent_span_id.hex(),
                            started_ns=str(record.start_time_unix_nano), ended_ns=str(record.end_time_unix_nano),
                            status=record.status.code))
                    else:
                        # Body may contain content. Retain only a known event identifier.
                        event = attrs.get('event.name', '')
                        if not event and record.body.WhichOneof('value') == 'string_value':
                            event = record.body.string_value
                        if event.removeprefix('claude_code.') not in EVENTS: event = 'claude_code.event'
                        append(self.record(attrs, signal='log', name=event,
                            timestamp_ns=str(record.time_unix_nano), trace_id=record.trace_id.hex(), span_id=record.span_id.hex()))
        return result

    def docker_arguments(self):
        return ['--env-file', str(self.environment)]

    def close(self):
        try:
            self.server.shutdown()
        finally:
            try:
                self.server.server_close()
                self.thread.join(5)
            finally:
                try:
                    with self.lock:
                        self.output.close()
                finally:
                    self.environment.unlink(missing_ok=True)
        if self.thread.is_alive():
            raise RuntimeError('receiver_close_unconfirmed')
