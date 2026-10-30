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

    skill_store: str | None = Field(
        default=None, validation_alias="LAOMEDO_SKILL_STORE", repr=False, exclude=True
    )
    frontend: str | None = Field(
        default=None,
        validation_alias="LANGFLOW_FRONTEND_PATH",
        repr=False,
        exclude=True,
    )

    def required_path(self, name: str) -> str:
        """Preserve the viewer's existing missing-environment KeyError contract."""
        value = getattr(self, name)
        if value is None:
            raise KeyError(type(self).model_fields[name].validation_alias)
        return value
