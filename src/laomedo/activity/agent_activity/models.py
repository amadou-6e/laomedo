"""Typed capture provenance and its reserved local invocation."""

from pydantic import BaseModel, ConfigDict, Field
from laomedo.activity.agent_activity.store import ActivityStore


class CaptureIdentity(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    owner: str = Field(min_length=1, max_length=200)
    flow: str = Field(min_length=1, max_length=200)
    node: str = Field(min_length=1, max_length=200)
    provider: str = "codex-cli"
    execution: str | None = None
    node_label: str | None = None

    @classmethod
    def from_values(
        cls, owner, flow, node, provider="codex-cli", *, execution=None, node_label=None
    ):
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
    model_config = ConfigDict(
        strict=True,
        frozen=True,
        arbitrary_types_allowed=True,
        extra="forbid",
        hide_input_in_errors=True,
    )
    store: ActivityStore = Field(repr=False)
    invocation_id: str
