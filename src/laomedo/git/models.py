"""Canonical private inputs to the shared host Git command boundary."""

from enum import Enum
from math import isnan
from pathlib import Path
from typing import Callable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from .settings import GIT_COMMAND_TIMEOUT_SECONDS


class GitEnvironmentProfile(str, Enum):
    """Isolation profiles; choosing a profile does not grant an effect."""

    WORKSPACE = "workspace"
    HOST_TRANSPORT = "host_transport"
    ISOLATED_HTTPS_READ_ONLY = "isolated_https_read_only"
    ISOLATED_FILE_READ_ONLY = "isolated_file_read_only"


class GitExecutionBudget(BaseModel):
    """Active output and operation budget; feature accounting stays with its caller."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    stdout_limit: int = Field(
        ge=0, description="Maximum spooled stdout bytes; equality remains allowed."
    )
    operation_deadline: float = Field(
        default=float("inf"),
        allow_inf_nan=True,
        description="Caller-owned absolute monotonic deadline, including an already expired value.",
    )
    poll_seconds: float = Field(
        default=0.05,
        gt=0,
        allow_inf_nan=False,
        description="Existing source polling interval in seconds.",
    )
    check_budget: Callable[[], None] | None = Field(
        default=None,
        repr=False,
        exclude=True,
        description="Optional caller-owned accounting check; its refusal propagates after cleanup.",
    )

    @field_validator("operation_deadline")
    @classmethod
    def validate_deadline(cls, value: float) -> float:
        """Allow an unbounded or expired deadline; NaN cannot disable comparisons."""
        if isnan(value):
            raise ValueError("git_read_deadline_invalid")
        return value


class GitTreeEntry(BaseModel):
    """Native tree metadata; its consumer retains mode/path admission decisions."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    mode: str = Field(
        description="Native Git tree mode, without adding stronger admission."
    )
    kind: str = Field(
        description="Native Git object kind, checked by the consumer before reading."
    )
    object_id: str = Field(
        description="Object identity returned by the admitted tree read."
    )


class GitCredential(BaseModel):
    """Private token binding for the GitHub-bound credential helper."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    token: SecretStr = Field(
        repr=False,
        exclude=True,
        description="Selected connection token, never normal model output.",
    )

    @field_validator("token")
    @classmethod
    def validate_token(cls, token: SecretStr) -> SecretStr:
        """Keep protocol delimiters out of credential-helper input."""
        value = token.get_secret_value()
        if not value or "\n" in value or "\r" in value:
            raise ValueError("credential_unavailable")
        return token


class GitExecutionContext(BaseModel):
    """Group isolation, configuration-home lifetime and command deadline policy."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    hooks_path: Path | None = Field(
        default=None,
        repr=False,
        exclude=True,
        description="Caller-owned disabled-hooks path for the isolated read profiles.",
    )
    profile: GitEnvironmentProfile = Field(
        default=GitEnvironmentProfile.HOST_TRANSPORT,
        description="Existing environment and stdin isolation profile.",
    )
    timeout: float = Field(
        default=GIT_COMMAND_TIMEOUT_SECONDS,
        gt=0,
        allow_inf_nan=False,
        description="Per-command deadline in seconds, supplied by the caller.",
    )
    home: Path | None = Field(
        default=None,
        repr=False,
        exclude=True,
        description="Explicit sequence-owned private home; absent means per-command isolation.",
    )
    hardened: bool = Field(
        default=False,
        description="Disable source-side fsmonitor and hooks using the isolated home.",
    )
    extra_env: dict[str, str] = Field(
        default_factory=dict,
        repr=False,
        exclude=True,
        description="Explicit caller overrides such as deterministic baseline commit dates.",
    )
    ignore_home_cleanup_errors: bool | None = Field(
        default=None,
        description="Existing caller home-cleanup policy; absent preserves the profile default.",
    )


class GitCommand(BaseModel):
    """One trusted host Git request, separate from caller authorization decisions."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    arguments: list[str] = Field(
        description="Native arguments after the Git executable; never include credential values."
    )
    directory: Path | None = Field(
        default=None,
        repr=False,
        exclude=True,
        description="Working repository for -C; absent for operations such as clone.",
    )
    context: GitExecutionContext = Field(
        description="Admitted isolation profile and lifetime/deadline policy."
    )
    configuration: list[tuple[str, str]] = Field(
        default_factory=list,
        description="Ordered explicit native -c settings; private credential helper settings are runner-owned.",
    )
    credential: GitCredential | None = Field(
        default=None,
        repr=False,
        exclude=True,
        description="Optional selected helper credential, excluded from normal serialization.",
    )

    cwd: Path | None = Field(
        default=None,
        repr=False,
        exclude=True,
        description="Native process cwd, distinct from the existing Git -C repository argument.",
    )
    budget: GitExecutionBudget | None = Field(
        default=None,
        exclude=True,
        description="Optional active spooled-output and caller accounting budget.",
    )

    @model_validator(mode="after")
    def validate_execution_profile(self) -> "GitCommand":
        """Reject attempts to weaken an isolated read profile, including mutable inputs."""
        isolated = self.context.profile in {
            GitEnvironmentProfile.ISOLATED_HTTPS_READ_ONLY,
            GitEnvironmentProfile.ISOLATED_FILE_READ_ONLY,
        }
        if not isolated:
            if self.budget is not None or self.cwd is not None:
                raise ValueError("git_read_profile_required")
            return self
        if (
            self.credential is not None
            or self.configuration
            or self.context.extra_env
            or self.context.hardened
            or self.context.home is not None
            or self.context.hooks_path is None
            or self.cwd is None
            or self.directory is not None
            or self.budget is None
            or not self.arguments
            or self.arguments[0]
            not in {
                "--version",
                "clone",
                "fetch",
                "for-each-ref",
                "rev-parse",
                "ls-tree",
                "cat-file",
            }
            or any(
                value.startswith(
                    ("-c", "-C", "--config", "--upload-pack", "--exec-path")
                )
                for value in self.arguments
            )
        ):
            raise ValueError("git_read_profile_invalid")
        return self
