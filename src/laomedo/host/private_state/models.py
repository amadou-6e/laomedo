"""Explicit process policy and private permission observations."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from laomedo.host.private_state.errors import PrivateStateError


class DirectoryPermissionPolicy(BaseModel):
    """Bind strict command locations, environment and one operation deadline."""

    model_config = ConfigDict(
        frozen=True, strict=True, extra="forbid", hide_input_in_errors=True
    )

    whoami: Path = Field(
        repr=False,
        exclude=True,
        description="Absolute trusted system identity executable.",
    )
    icacls: Path = Field(
        repr=False,
        exclude=True,
        description="Absolute trusted system permission executable.",
    )
    environment: dict[str, str] = Field(
        repr=False,
        exclude=True,
        description="Explicit filtered invocation environment, never ambient credentials.",
    )
    deadline: float = Field(
        gt=0,
        allow_inf_nan=False,
        repr=False,
        exclude=True,
        description="Absolute monotonic request-admission deadline.",
    )

    def timeout_seconds(self, ceiling: float, now: float) -> float:
        """Clamp one subprocess to remaining time without resetting its budget."""
        remaining = self.deadline - now
        if remaining <= 0:
            raise PrivateStateError("private_state_deadline_exceeded")
        return min(ceiling, remaining)


class DirectoryPermissionResult(BaseModel):
    """Retain the already observed owner privately for descriptor verification."""

    model_config = ConfigDict(
        frozen=True, strict=True, extra="forbid", hide_input_in_errors=True
    )

    owner_sid: str | None = Field(
        default=None,
        repr=False,
        exclude=True,
        description="Observed Windows user SID; absent for POSIX chmod.",
    )
