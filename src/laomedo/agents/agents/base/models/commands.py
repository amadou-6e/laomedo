"""Commands values owned by the shared Agent capability."""

from laomedo.agents.agents.base.models.runtime import CleanupObservation
from pydantic import BaseModel, ConfigDict, Field, model_validator


class CommandRequest(BaseModel):
    """One admitted workspace command; no credential or executable selection authority."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    command: str | None = Field(
        default=None,
        min_length=1,
        repr=False,
        description="Command text to admit under provider-local workspace policy.",
    )
    deadline: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Absolute host monotonic deadline; None retains provider's bounded default.",
    )

    argv: list[str] | None = Field(
        default=None,
        min_length=1,
        repr=False,
        description="Exact admitted native argv for fixed probes; mutually exclusive with shell text.",
    )

    @model_validator(mode="after")
    def validate_command_form(self):
        """Admit one explicit command representation without shell coercion."""
        if (self.command is None) == (self.argv is None):
            raise ValueError("one_command_form_required")
        return self


class CommandResult(BaseModel):
    """Native command outcome plus independently observed resource cleanup."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    exit_code: int = Field(
        description="Native exit status, including provider's established timeout/cancellation mapping."
    )
    stdout: str = Field(
        default="",
        repr=False,
        description="Bounded decoded standard output; not diagnostic authorization evidence.",
    )
    stderr: str = Field(
        default="",
        repr=False,
        description="Bounded decoded standard error when the provider exposes separate streams.",
    )
    cleanup: CleanupObservation = Field(
        description="Cleanup evidence for resources allocated by this command."
    )
