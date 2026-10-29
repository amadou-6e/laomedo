"""Canonical private inputs to the shared host Git command boundary."""

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from .settings import GIT_COMMAND_TIMEOUT_SECONDS


class GitEnvironmentProfile(str, Enum):
    """Existing isolation profiles; choosing a profile does not grant an effect."""

    WORKSPACE = "workspace"
    HOST_TRANSPORT = "host_transport"


class GitCredential(BaseModel):
    """Private token binding for the existing GitHub-bound credential helper."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    token: SecretStr = Field(repr=False, exclude=True, description="Selected connection token, never normal model output.")

    @field_validator("token")
    @classmethod
    def validate_token(cls, token: SecretStr) -> SecretStr:
        """Keep protocol delimiters out of the existing credential helper input."""
        value = token.get_secret_value()
        if not value or "\n" in value or "\r" in value:
            raise ValueError("credential_unavailable")
        return token


class GitExecutionContext(BaseModel):
    """Group isolation, configuration-home lifetime and command deadline policy."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    profile: GitEnvironmentProfile = Field(default=GitEnvironmentProfile.HOST_TRANSPORT, description="Existing environment and stdin isolation profile.")
    timeout: float = Field(default=GIT_COMMAND_TIMEOUT_SECONDS, gt=0, allow_inf_nan=False, description="Per-command deadline in seconds, supplied by the caller.")
    home: Path | None = Field(default=None, repr=False, exclude=True, description="Explicit sequence-owned private home; absent means per-command isolation.")
    hardened: bool = Field(default=False, description="Disable source-side fsmonitor and hooks using the isolated home.")
    extra_env: dict[str, str] = Field(default_factory=dict, repr=False, exclude=True, description="Explicit caller overrides such as deterministic baseline commit dates.")
    ignore_home_cleanup_errors: bool | None = Field(default=None, description="Existing caller home-cleanup policy; absent preserves the profile default.")


class GitCommand(BaseModel):
    """One trusted host Git request, separate from caller authorization decisions."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    arguments: list[str] = Field(description="Native arguments after the Git executable; never include credential values.")
    directory: Path | None = Field(default=None, repr=False, exclude=True, description="Working repository for -C; absent for operations such as clone.")
    context: GitExecutionContext = Field(description="Admitted isolation profile and lifetime/deadline policy.")
    configuration: list[tuple[str, str]] = Field(default_factory=list, description="Ordered explicit native -c settings; private credential helper settings are runner-owned.")
    credential: GitCredential | None = Field(default=None, repr=False, exclude=True, description="Optional selected helper credential, excluded from normal serialization.")
