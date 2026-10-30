"""Typed capture provenance and its reserved local invocation."""

from pydantic import BaseModel, ConfigDict, Field
from laomedo.agents.activity.store import ActivityStore


class CaptureIdentity(BaseModel):
    """Immutable owner, graph and node provenance admitted before capture starts."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    owner: str = Field(min_length=1, max_length=200, description="Authenticated owner of the retained invocation.")
    flow: str = Field(min_length=1, max_length=200, description="Graph identity associated with this invocation.")
    node: str = Field(min_length=1, max_length=200, description="Stable graph node identity for this capture.")
    provider: str = Field(default="codex-cli", description="Existing native Activity provider identifier.")
    execution: str | None = Field(default=None, description="Graph execution identity when supplied by the caller.")
    node_label: str | None = Field(default=None, description="Saved human-readable node label, if available.")

    @classmethod
    def from_values(
        cls, owner, flow, node, provider="codex-cli", *, execution=None, node_label=None
    ):
        """Validate external identity values while preserving the stable boundary error."""
        # Stable boundary error, before Pydantic constructs the trusted value.
        if not all(
            isinstance(value, str) and value and len(value) <= 200
            for value in (owner, flow, node)
        ):
            raise ValueError("agent_activity_identity_required")
        return cls(
            owner=owner,
            flow=flow,
            node=node,
            provider=provider,
            execution=execution,
            node_label=node_label,
        )


class ActivityInvocation(BaseModel):
    """Pair the internal store handle with its reserved invocation identity."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        arbitrary_types_allowed=True,
        extra="forbid",
        hide_input_in_errors=True,
    )
    store: ActivityStore = Field(repr=False, description="Internal store owning the reserved capture, never login material.")
    invocation_id: str = Field(description="Durable invocation identity returned by the store reservation.")
