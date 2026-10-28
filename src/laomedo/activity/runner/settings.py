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

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read at point of use; no cached environment, dotenv or credential contents.

    Strings preserve missing/empty values and exact ``== "1"`` flag behavior.
    Existing consumers own URL/path validation and stable public errors.
    """

    model_config = SettingsConfigDict(
        case_sensitive=True, env_file=None, secrets_dir=None,
        env_nested_delimiter=None, enable_decoding=False,
        extra="ignore", frozen=True, hide_input_in_errors=True,
    )

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings,
                                   dotenv_settings, file_secret_settings):
        """Only explicit arguments and the process environment supply settings."""
        return init_settings, env_settings

    otel: str | None = Field(default=None, validation_alias='LAOMEDO_RUNNER_OTEL', repr=False, exclude=True)
