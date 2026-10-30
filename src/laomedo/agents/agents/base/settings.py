"""Shared HTTP limits, snapshot bounds and runner startup configuration."""

MAX_BODY = 64 * 1024


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

    startup_gate: str | None = Field(default=None, validation_alias='LAOMEDO_STARTUP_GATE', repr=False, exclude=True)
