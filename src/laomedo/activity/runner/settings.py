"""Feature settings and fixed protocol values; mutable state has one owner."""

from __future__ import annotations

ALLOWED = frozenset(
    {
        "conversation.id",
        "thread.id",
        "thread_id",
        "turn.id",
        "turn_id",
        "call.id",
        "call_id",
        "event.name",
        "model",
        "model_name",
        "gen_ai.request.model",
        "gen_ai.response.model",
        "input_token_count",
        "output_token_count",
        "cached_input_token_count",
        "reasoning_output_token_count",
        "tool_name",
        "duration_ms",
        "cached_token_count",
        "cache_write_token_count",
        "reasoning_token_count",
        "sender_thread_id",
        "receiver_thread_id",
        "communication_id",
        "event.timestamp",
        "event.kind",
    }
)
