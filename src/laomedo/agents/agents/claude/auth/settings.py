"""Feature settings and fixed protocol values; mutable state has one owner."""

from __future__ import annotations

CODES = frozenset(
    {
        "claude_host_login_unavailable",
        "claude_host_login_expired",
        "claude_local_login_copy_failed",
    }
)

# Normal copy admission and a distinct exact-cleanup reserve. These are operation
# policies, not a verification allowance or a hard wall-time guarantee.
COPY_SECONDS = 90.0
CLEANUP_SECONDS = 20.0

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read at point of use; no cached environment, dotenv or credential contents.

    Strings preserve missing/empty values and exact ``== "1"`` flag behavior.
    Existing consumers own URL/path validation and stable public errors.
    """

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=None,
        secrets_dir=None,
        env_nested_delimiter=None,
        enable_decoding=False,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """Only explicit arguments and the process environment supply settings."""
        return init_settings, env_settings

    mirror_host_login: str | None = Field(
        default=None,
        validation_alias="LAOMEDO_CLAUDE_MIRROR_HOST_LOGIN",
        repr=False,
        exclude=True,
    )
    private_state_directory: str | None = Field(
        default=None,
        validation_alias="LAOMEDO_CLAUDE_LOGIN_STATE_DIR",
        repr=False,
        exclude=True,
        description="Trusted host override for private copy receipts outside checkouts.",
    )
