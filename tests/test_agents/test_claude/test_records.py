"""Independent record projections and boundary values; internal regressions."""

import unittest
import json
from laomedo.agents.activity.models import ActivityAttemptRecord
from laomedo.agents.agents.claude.activity.models import ClaudeTelemetryEnvironment
from support.model_assertions import assert_secrets_excluded


class ClaudeRecordTests(unittest.TestCase):
    """Keep literal expected records independent of production serializers."""

    def test_claude_telemetry_preserves_exact_privacy_environment(self):
        model = ClaudeTelemetryEnvironment(
            endpoint="http://127.0.0.1:8000", token="private-otel"
        )
        assert_secrets_excluded(self, model, ("private-otel",))
        self.assertEqual(
            model.to_environment(),
            {
                "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
                "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
                "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
                "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:8000",
                "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Bearer private-otel",
                "OTEL_METRICS_EXPORTER": "otlp",
                "OTEL_LOGS_EXPORTER": "otlp",
                "OTEL_TRACES_EXPORTER": "otlp",
                "OTEL_METRIC_EXPORT_INTERVAL": "1000",
                "OTEL_LOGS_EXPORT_INTERVAL": "1000",
                "OTEL_TRACES_EXPORT_INTERVAL": "1000",
                "OTEL_LOG_USER_PROMPTS": "0",
                "OTEL_LOG_ASSISTANT_RESPONSES": "0",
                "OTEL_LOG_TOOL_DETAILS": "0",
                "OTEL_LOG_TOOL_CONTENT": "0",
                "OTEL_METRICS_INCLUDE_ACCOUNT_UUID": "false",
            },
        )

    def test_claude_attempt_preserves_original_serialized_field_order(self):
        expected = dict(
            id="attempt",
            native_start=2,
            otel_start=3,
            usage_baseline={"thread": {"native_extension": None}},
            native_end=None,
            fresh_thread=False,
            otel_end=None,
            status="running",
            ended_at=None,
        )
        record = ActivityAttemptRecord(**expected).to_claude_record()
        self.assertEqual(record, expected)
        self.assertEqual(
            list(record),
            [
                "id",
                "native_start",
                "otel_start",
                "usage_baseline",
                "native_end",
                "fresh_thread",
                "otel_end",
                "status",
                "ended_at",
            ],
        )
        self.assertEqual(json.dumps(record), json.dumps(expected))
