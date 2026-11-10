"""Explicit app configuration and fixed GitHub OAuth protocol policy."""

from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_CALLBACK_PATH = "/api/v1/laomedo/github-connections/callback"
OAUTH_RESPONSE_LIMIT = 65536
OAUTH_DEADLINE_SECONDS = 30
GITHUB_API_ORIGIN = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"
GITHUB_READ_RESPONSE_LIMIT = 8 * 1024 * 1024
GITHUB_READ_TOTAL_BYTES = 128 * 1024 * 1024
GITHUB_READ_DEADLINE_SECONDS = 60
GITHUB_REPOSITORY_LIMIT = 1000
CONNECTION_ATTEMPT_SECONDS = 600
CONNECTION_PENDING_LIMIT = 32
GITHUB_REF_LIMIT = 32
GITHUB_TAG_DEPTH = 16


class GitHubAppSettings(BaseSettings):
    """Admit operator input without environment, dotenv or keyring discovery."""

    model_config = SettingsConfigDict(
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
        env_file=None,
        secrets_dir=None,
    )

    client_id: str = Field(
        strict=True,
        pattern=r"^[A-Za-z0-9_.-]{1,128}$",
        description="GitHub App client ID deliberately configured by its owner.",
    )
    slug: str = Field(
        strict=True,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        max_length=100,
        description="Exact GitHub App slug for its installation page.",
    )
    client_secret: SecretStr = Field(
        exclude=True,
        repr=False,
        min_length=1,
        max_length=4096,
        description="App secret loaded explicitly from native vault custody.",
    )
    callback_uri: str = Field(
        strict=True,
        description="Exact registered native loopback callback URI.",
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
        """Use only explicit operator configuration, never ambient credentials."""
        return (init_settings,)

    @field_validator("callback_uri")
    @classmethod
    def fixed_callback(cls, value: str) -> str:
        """Refuse aliases, paths, credentials, fragments and callback overrides."""
        url = urlsplit(value)
        if (
            url.scheme != "http"
            or url.hostname != "127.0.0.1"
            or url.port is None
            or not 1024 <= url.port <= 65535
            or url.netloc != f"127.0.0.1:{url.port}"
            or url.path != GITHUB_CALLBACK_PATH
            or url.query
            or url.fragment
        ):
            raise ValueError("github_callback_invalid")
        return value

    @property
    def installation_url(self) -> str:
        """Return the configured app's fixed HTTPS repository installation page."""
        return f"https://github.com/apps/{self.slug}/installations/new"
