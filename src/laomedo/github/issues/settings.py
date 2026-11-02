"""Host-provided configuration for this feature."""

from __future__ import annotations

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

    url: str = Field(
        default="",
        validation_alias="LAOMEDO_GITHUB_ISSUE_URL",
        repr=False,
        exclude=True,
    )
    token_file: str = Field(
        default="/run/secrets/laomedo-runner-token",
        validation_alias="LAOMEDO_GITHUB_ISSUE_TOKEN_FILE",
        repr=False,
        exclude=True,
    )
