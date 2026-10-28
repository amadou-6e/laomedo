"""Feature settings and fixed protocol values; mutable state has one owner."""

from __future__ import annotations

REFUSALS = {
    "runner_busy",
    "run_not_dispatchable",
    "resume_binding_mismatch",
    "post_run_snapshot_mismatch",
    "workspace_changed_since_snapshot",
    "protected_mount_changed",
    "activity_attempt_already_exists",
    "publication_handoff_resume_denied",
    "resume_after_runner_restart_forbidden",
    "resume_auth_identity_mismatch",
}

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

    database: str | None = Field(default=None, validation_alias='LAOMEDO_AGENT_ACTIVITY_DB', repr=False, exclude=True)
