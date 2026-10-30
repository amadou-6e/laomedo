"""Typed capture provenance and its reserved local invocation."""

from pydantic import BaseModel, ConfigDict, Field
from pydantic import JsonValue
from laomedo.agents.activity.store import ActivityStore


class CaptureIdentity(BaseModel):
    """Immutable owner, graph and node provenance admitted before capture starts."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    owner: str = Field(
        min_length=1,
        max_length=200,
        description="Authenticated owner of the retained invocation.",
    )
    flow: str = Field(
        min_length=1,
        max_length=200,
        description="Graph identity associated with this invocation.",
    )
    node: str = Field(
        min_length=1,
        max_length=200,
        description="Stable graph node identity for this capture.",
    )
    provider: str = Field(
        default="codex-cli", description="Existing native Activity provider identifier."
    )
    execution: str | None = Field(
        default=None,
        description="Graph execution identity when supplied by the caller.",
    )
    node_label: str | None = Field(
        default=None, description="Saved human-readable node label, if available."
    )

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
    store: ActivityStore = Field(
        repr=False,
        description="Internal store owning the reserved capture, never login material.",
    )
    invocation_id: str = Field(
        description="Durable invocation identity returned by the store reservation."
    )


class ActivityAttemptRecord(BaseModel):
    """New native-capture attempt, with later mutable transitions service-owned."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    id: str = Field(description="Admitted capture attempt UUID.")
    native_start: int = Field(
        description="Observed initial native receipt line offset."
    )
    otel_start: int = Field(description="Observed initial OTLP receipt line offset.")
    native_end: int | None = Field(
        description="Explicit null until native receipt closure is observed."
    )
    otel_end: int | None = Field(
        description="Explicit null until OTLP receipt closure is observed."
    )
    fresh_thread: bool | None = Field(
        default=None,
        description="Observed new-thread boundary, omitted when provider does not attest it.",
    )
    usage_baseline: dict[str, JsonValue] = Field(
        description="Thread-indexed native cumulative counter evidence; provider extensions preserved."
    )
    status: str = Field(description="Existing initial capture state, running.")
    ended_at: str | None = Field(description="Explicit null until the attempt ends.")

    def to_record(self) -> dict:
        """Preserve the existing provider variants without inventing end evidence."""
        return self.model_dump(exclude_unset=True)


class TokenUsage(BaseModel):
    """The six validated normalized token counters, with existing wire names."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
        populate_by_name=True,
    )
    input_tokens: int = Field(
        ge=0,
        alias="inputTokens",
        description="All input tokens, including cached reads/writes.",
    )
    cached_input_tokens: int = Field(
        ge=0, alias="cachedInputTokens", description="Input tokens read from cache."
    )
    cache_write_input_tokens: int = Field(
        ge=0,
        alias="cacheWriteInputTokens",
        description="Input tokens written to cache.",
    )
    output_tokens: int = Field(
        ge=0,
        alias="outputTokens",
        description="All output tokens, including reasoning.",
    )
    reasoning_output_tokens: int = Field(
        ge=0,
        alias="reasoningOutputTokens",
        description="Output tokens attributed to reasoning.",
    )
    total_tokens: int = Field(
        ge=0,
        alias="totalTokens",
        description="Existing input-plus-output total without double-counting cache/reasoning.",
    )

    def to_payload(self) -> dict[str, int]:
        """Project the exact normalized counter names expected by Activity consumers."""
        return self.model_dump(by_alias=True)
