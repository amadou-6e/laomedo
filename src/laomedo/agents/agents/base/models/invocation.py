"""Invocation values owned by the shared Agent capability."""

from laomedo.agents.agents.base.base.invocation import BasePostFreezeSettlement
from laomedo.agents.agents.base.models.failures import FailureObservation
from laomedo.agents.agents.base.models.runtime import RuntimeCleanupReport
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator
from typing import Literal


class InvocationContext(BaseModel):
    """Host context for one admitted invocation; persisted attempt identity is retained."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    run_id: str = Field(min_length=1, description="Existing host run identity.")
    attempt_id: str = Field(
        min_length=1, description="Current admitted attempt identity."
    )
    workspace: Path = Field(repr=False, description="Admitted execution workspace.")
    evidence: Path = Field(repr=False, description="Private evidence location.")
    record: dict[str, JsonValue] = Field(
        repr=False,
        description="Detached record snapshot; journal owns actual persistence.",
    )


class InvocationRequest(BaseModel):
    """Admitted host execution request; never deserialized directly from graph input."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    context: InvocationContext = Field(description="Owning host attempt context.")
    task: str = Field(repr=False, description="Admitted task text.")
    model: str = Field(description="Explicit selected native model, never substituted.")
    effort: str | None = Field(description="Explicit native effort when selected.")
    resume: bool = Field(
        description="Load the saved native conversation without Fresh fallback."
    )
    native_session: str | None = Field(description="Saved native identity on Resume.")
    deadline: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Native attempt deadline only where existing policy supplies one.",
    )

    @model_validator(mode="after")
    def validate_conversation_mode(self):
        """No missing Resume binding or preselected native identity on Fresh."""
        if self.resume != bool(self.native_session):
            raise ValueError("attempt_native_binding_mismatch")
        return self


class SettlementView(BaseModel):
    """Detached Agent record after freeze or failure, never the live mutable record."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    record: dict[str, JsonValue] = Field(
        repr=False, description="Deep-copied current persisted fields."
    )


class SettlementUpdates(BaseModel):
    """Declared settlement-owned fields; Agent alone owns status/demotion."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    container_ownership: dict[str, JsonValue] | None = Field(
        default=None,
        repr=False,
        description="Existing exact cleanup/grant ownership fields.",
    )
    controller_cleanup: Literal["confirmed", "unverified"] | None = Field(
        default=None, description="Observed controller closure."
    )
    publication_handoff: dict[str, JsonValue] | None = Field(
        default=None, repr=False, description="Existing host publication handoff state."
    )
    evidence: dict[str, JsonValue] = Field(
        default_factory=dict,
        repr=False,
        description="Provider-native evidence, not shared record-state overrides.",
    )

    @model_validator(mode="after")
    def reject_state_override(self):
        if {
            "status",
            "cancel_requested",
            "cancel_confirmed",
            "snapshot_ready",
            "post_run_hash",
            "output_ref",
            "error_category",
        } & self.evidence.keys():
            raise ValueError("reserved_settlement_evidence")
        return self


class SettlementResult(BaseModel):
    """Settlement cleanup truth and declared updates for Agent-owned persistence."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    verified: bool = Field(
        description="Confirmed settlement cleanup, not inferred publication success."
    )
    detail: str | None = Field(default=None, description="Safe scoped cleanup detail.")
    code: str | None = Field(
        default=None, description="Existing stable failure category."
    )
    updates: SettlementUpdates = Field(
        default_factory=SettlementUpdates,
        repr=False,
        description="Declared detached settlement updates applied by Agent.",
    )


class InvocationResult(BaseModel):
    """Native invocation result before Agent freeze and surviving lease settlement."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
        arbitrary_types_allowed=True,
    )
    status: Literal[
        "completed", "failed", "cancelled", "unknown", "timeout", "interrupted"
    ] = Field(description="Native attempt outcome.")
    native_session: str | None = Field(
        description="Actual native conversation identity, if bound."
    )
    answer: str | None = Field(
        default=None, repr=False, description="Native terminal output."
    )
    turns: tuple[dict[str, JsonValue], ...] = Field(
        description="Detached native turn records."
    )
    error_category: str | None = Field(
        default=None,
        description="Unchanged public category, separate from allowlisted private diagnostics.",
    )
    failure: FailureObservation | None = Field(
        default=None, description="Safe original failure evidence."
    )
    cleanup: RuntimeCleanupReport = Field(
        description="Exact owned resource cleanup facts."
    )
    settlement: BasePostFreezeSettlement | None = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Host-only supervision surviving run, for any outcome status.",
    )
