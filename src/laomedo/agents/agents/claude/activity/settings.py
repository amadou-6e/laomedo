"""Feature settings and fixed protocol values; mutable state has one owner."""

from __future__ import annotations

from laomedo.agents.activity.runner.settings import ALLOWED

SAFE = ALLOWED | frozenset(
    {
        "session.id",
        "event.sequence",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
        "cost_usd",
        "duration_ms",
        "success",
        "status_code",
        "error.type",
        "error_category",
        "type",
        "tool_name",
        "tool_use_id",
        "interaction.sequence",
        "api_request_id",
        "service.name",
        "service.version",
        "span.type",
        "gen_ai.system",
        "tool_name_safe",
        "error_class",
        "effort",
        "request_id",
        "client_request_id",
        "gen_ai.response.id",
        "attempt",
        "ttft_ms",
        "first_content_ms",
        "interaction.duration_ms",
        "result_tokens",
        "gen_ai.tool.call.id",
    }
)


EVENTS = frozenset(
    {
        "user_prompt",
        "assistant_response",
        "tool_result",
        "api_request",
        "api_error",
        "api_refusal",
        "tool_decision",
        "permission_mode_changed",
        "auth",
        "mcp_server_connection",
        "internal_error",
        "plugin_installed",
        "plugin_loaded",
        "skill_activated",
        "at_mention",
        "api_retries_exhausted",
        "hook_registered",
        "hook_execution_start",
        "hook_execution_complete",
        "hook_plugin_metrics",
        "compaction",
        "subagent_completed",
        "feedback_survey",
        "retention_sweep",
        "managed_settings_resolved",
        "safety",
    }
)
