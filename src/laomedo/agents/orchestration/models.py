"""Handoff values after existing admission; controllers retain effects."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_serializer
from laomedo.agents.artifacts.models import ArtifactReference


class HandoffSource(BaseModel):
    """Source identity only; legacy observational values retain their JSON types."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    provider: JsonValue = Field(description="Source provider observation, not an authority grant.")
    run_id: JsonValue = Field(description="Source run observation; admission is caller-owned.")


class HandoffTarget(BaseModel):
    """Target provider and optional caller metadata, preserving omitted keys."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    provider: Literal["codex", "claude", "opencode"] = Field(description="Provider admitted by the current handoff contract.")
    agent: JsonValue = Field(default=None, description="Optional legacy agent metadata; omitted unless supplied.")
    model: JsonValue = Field(default=None, description="Optional native model selection; exact legacy JSON value retained.")
    effort: JsonValue = Field(default=None, description="Optional native effort selection; omitted unless supplied.")


class HandoffPrior(BaseModel):
    """Exact prior bindings selected by the existing resume admission path."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    provider: JsonValue = Field(description="Prior provider, already compared to the target.")
    run_id: JsonValue = Field(description="Prior source run identity.")
    thread_id: JsonValue = Field(description="Prior native conversation binding.")
    post_run_hash: JsonValue = Field(description="Prior verified working-state binding.")
    model: JsonValue = Field(description="Prior native model value, preserving legacy admission.")
    effort: JsonValue = Field(description="Prior native effort value, preserving legacy admission.")


class HandoffSkillReference(BaseModel):
    """Pinned skill byte identity after the legacy envelope checks."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    skill_id: str | int = Field(description="Existing admission accepts names and nonnegative digit-only integer IDs.")
    revision_id: str = Field(description="Admitted sha256 byte revision identity.")
    tree_hash: str = Field(description="The same admitted immutable byte identity.")


class HandoffProvenance(BaseModel):
    """The four safe coordination fields accepted by a runner's Fresh request."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    execution_id: str = Field(description="Coordination execution identity.")
    step: int = Field(description="Controller step; the runner enforces its admission rules.")
    source: HandoffSource | None = Field(description="Explicit source identity or null for an initial step.")
    workspace_policy: Literal["independent", "resume_bound"] = Field(description="Existing workspace isolation/binding policy.")


class AgentHandoff(BaseModel):
    """One coherent next-step envelope; no execution or authority is implied."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    schema_version: Literal[1] = Field(default=1, description="Existing envelope schema version.")
    execution_id: JsonValue = Field(description="Caller execution identity; legacy envelope admission is retained.")
    step: JsonValue = Field(description="Caller step observation; runner admission remains unchanged.")
    source: HandoffSource | None = Field(description="Selected source identity, explicitly null for a first step.")
    target: HandoffTarget = Field(description="Selected native provider and optional model metadata.")
    task: str = Field(description="Explicit nonempty next-step instruction.")
    skill_refs: list[HandoffSkillReference] = Field(description="Unique pinned skills in caller order.")
    workspace_policy: Literal["independent", "resume_bound"] = Field(description="Fresh isolation or native resume binding.")
    operation: Literal["fresh", "resume"] = Field(description="Admitted runner operation.")
    artifacts: list[ArtifactReference] = Field(description="Individually admitted source files; never allowed on resume.")
    prior: HandoffPrior | None = Field(description="Explicit resume bindings, null for a Fresh handoff.")

    @field_serializer("target")
    def serialize_target(self, value: HandoffTarget) -> dict:
        """Do not invent null model/effort/agent keys absent in a legacy target."""
        return value.model_dump(exclude_unset=True)

    def to_payload(self) -> dict:
        """Preserve the existing eleven-field envelope and explicit source/prior nulls."""
        return self.model_dump()
