"""Host-local readiness observations, independent of public service payloads."""

from pydantic import BaseModel, ConfigDict, Field


class DockerReadiness(BaseModel):
    """One completed read-only check; an absent observation means unconfirmed."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    reason: str | None = Field(
        description="Stable failure code, or None for confirmed readiness."
    )
    checked_at: float = Field(
        description="Process-local monotonic completion time; never a persisted timestamp."
    )
