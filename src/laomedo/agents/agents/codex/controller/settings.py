"""Validated host settings for the native SDK attachment, separate from flags."""

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from laomedo.agents.errors import RunnerError


class Settings(BaseSettings):
    """Load positive transport budgets without dotenv, secret stores or caching."""

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=None,
        secrets_dir=None,
        enable_decoding=False,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )
    max_bytes: int = Field(
        default=64 * 1024 * 1024,
        gt=0,
        validation_alias="LAOMEDO_CODEX_STREAM_MAX_BYTES",
        description="Combined stdout/stderr byte ceiling per native controller attachment.",
    )
    startup_margin: float = Field(
        default=120,
        gt=0,
        allow_inf_nan=False,
        validation_alias="LAOMEDO_CODEX_STREAM_STARTUP_MARGIN",
        description="Additional attachment seconds around the existing allowed native turns.",
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
        """Read only explicit arguments and current host environment values."""
        return init_settings, env_settings

    @classmethod
    def load(cls) -> "Settings":
        """Translate invalid host budgets before dispatch into a descriptive code.

        Returns
        -------
        Settings
            Current validated positive finite transport limits.

        Raises
        ------
        RunnerError
            Host stream settings are invalid; no controller has been started.
        """
        try:
            return cls()
        except ValidationError:
            raise RunnerError("runner_transport_configuration_invalid") from None
