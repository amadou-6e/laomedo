"""Trusted private-browser deployment configuration; never credential storage."""

from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PRIVATE_SESSION_COOKIE_NAME = "laomedo_private_session"


class PrivateBrowserSettings(BaseSettings):
    """Explicit loopback origin and owned private directory, without ambient input."""

    model_config = SettingsConfigDict(
        env_file=None,
        secrets_dir=None,
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
    )

    origin: str = Field(strict=True, description="Exact native profile app origin.")
    runtime_root: Path = Field(
        description="Admitted private state outside public stores."
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
        return (init_settings,)

    @field_validator("origin")
    @classmethod
    def exact_loopback_origin(cls, value):
        url = urlsplit(value)
        if (
            url.scheme != "http"
            or url.hostname != "127.0.0.1"
            or url.port is None
            or not 1024 <= url.port <= 65535
            or url.netloc != f"127.0.0.1:{url.port}"
            or url.path
            or url.query
            or url.fragment
        ):
            raise ValueError("private_origin_invalid")
        return value

    @field_validator("runtime_root")
    @classmethod
    def absolute_runtime(cls, value):
        if not value.is_absolute():
            raise ValueError("private_runtime_invalid")
        return value
