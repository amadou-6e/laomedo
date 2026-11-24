"""Claude's native telemetry policy; the private exporter sink is explicit."""

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ClaudeTelemetryEnvironment(BaseModel):
    """Exporter endpoint and credential, with content capture disabled by policy."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    endpoint: str = Field(
        description="Trusted local OTLP receiver URL created by this capture."
    )
    token: SecretStr = Field(
        repr=False,
        exclude=True,
        description="Per-capture bearer token, never ordinary dumps or repr.",
    )

    def to_environment(self) -> dict[str, str]:
        """Unwrap only for the existing private native exporter environment."""
        return {
            "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
            "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
            "OTEL_EXPORTER_OTLP_ENDPOINT": self.endpoint,
            "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Bearer "
            + self.token.get_secret_value(),
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
        }
