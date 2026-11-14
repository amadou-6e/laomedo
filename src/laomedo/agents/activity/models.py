"""Typed capture provenance and its reserved local invocation."""

from pydantic import BaseModel, ConfigDict, Field, SkipValidation
from pydantic import JsonValue
from pydantic import model_validator
from datetime import datetime
from typing import Annotated, Literal
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

    def to_claude_record(self) -> dict:
        """Retain Claude's historical field order as well as unknown values."""
        value = self.to_record()
        order = (
            "id",
            "native_start",
            "otel_start",
            "usage_baseline",
            "native_end",
            "fresh_thread",
            "otel_end",
            "status",
            "ended_at",
        )
        return {key: value[key] for key in order if key in value}


class ActivityProjection(BaseModel):
    """Strict app metadata around existing, reference-preserving observations.

    SkipValidation applies only to externally observed native-bearing structures.
    Their existing partial/unknown values are not normalized token counters. Use
    the explicit wire projections instead of recursive Pydantic serialization.
    Frozen fields do not make the retained nested observations immutable.
    """

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    turns: SkipValidation[list[dict[str, JsonValue]]] = Field(
        repr=False,
        description="Existing observed turn lanes; native extensions retained.",
    )
    items: SkipValidation[list[dict[str, JsonValue]]] = Field(
        repr=False,
        description="Existing observed native item records, without copying.",
    )
    threads: SkipValidation[list[dict[str, JsonValue]]] = Field(
        repr=False,
        description="Existing observed thread metadata and native extensions.",
    )
    diagnostics: SkipValidation[list[dict[str, JsonValue]] | None] = Field(
        default=None,
        repr=False,
        description="Existing native diagnostics; omission differs from an explicit empty list or null.",
    )
    telemetry: SkipValidation[list[dict[str, JsonValue]]] = Field(
        repr=False,
        description="Existing observed telemetry including arbitrary native attributes.",
    )
    telemetry_coverage: str = Field(
        description="Application explanation of observed telemetry completeness."
    )
    uncorrelated_thread_count: int = Field(
        description="Application count of observed threads outside the selected scope."
    )
    usage: SkipValidation[dict[str, JsonValue] | None] = Field(
        repr=False,
        description="Existing inclusive native usage; partial counters and unknown null retained.",
    )
    usage_by_thread: SkipValidation[dict[str, dict[str, JsonValue] | None]] = Field(
        repr=False,
        description="Existing thread-indexed native snapshots, including partial and unknown usage.",
    )
    usage_points: SkipValidation[list[dict[str, JsonValue]]] = Field(
        repr=False,
        description="Existing observed usage points with native extensions and cost evidence.",
    )
    clock: str = Field(
        description="Application explanation of the projection's timestamp source."
    )
    cost: SkipValidation[dict[str, JsonValue]] = Field(
        repr=False,
        description="Existing observed pricing evidence and unknown estimates, without normalization.",
    )
    cost_reason: str = Field(
        description="Application explanation of the projected cost basis or uncertainty."
    )

    @classmethod
    def empty(cls):
        """Represent an invocation with no retained observations or known usage."""
        return cls(
            turns=[],
            items=[],
            threads=[],
            diagnostics=[],
            telemetry=[],
            telemetry_coverage="not observed",
            uncorrelated_thread_count=0,
            usage=None,
            usage_by_thread={},
            usage_points=[],
            clock="runner receipt time",
            cost={"amount": None, "per_thread": {}, "reason": "No activity observed."},
            cost_reason="No activity observed.",
        )

    def to_payload(self) -> dict[str, JsonValue]:
        """Return shared wire order and original references, preserving omission."""
        value = {"turns": self.turns, "items": self.items, "threads": self.threads}
        if "diagnostics" in self.model_fields_set:
            value["diagnostics"] = self.diagnostics
        value.update(
            telemetry=self.telemetry,
            telemetry_coverage=self.telemetry_coverage,
            uncorrelated_thread_count=self.uncorrelated_thread_count,
            usage=self.usage,
            usage_by_thread=self.usage_by_thread,
            usage_points=self.usage_points,
            clock=self.clock,
            cost=self.cost,
            cost_reason=self.cost_reason,
        )
        return value

    def to_usage_first_payload(self) -> dict[str, JsonValue]:
        """Return the existing OpenCode usage-first wire order without copying values."""
        return {
            "turns": self.turns,
            "items": self.items,
            "threads": self.threads,
            **(
                {"diagnostics": self.diagnostics}
                if "diagnostics" in self.model_fields_set
                else {}
            ),
            "usage": self.usage,
            "usage_by_thread": self.usage_by_thread,
            "usage_points": self.usage_points,
            "telemetry": self.telemetry,
            "telemetry_coverage": self.telemetry_coverage,
            "uncorrelated_thread_count": self.uncorrelated_thread_count,
            "clock": self.clock,
            "cost": self.cost,
            "cost_reason": self.cost_reason,
        }


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


class MessageActivity(BaseModel):
    """Replacement text snapshot for one message, scoped by native thread and ID."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    removed: bool = Field(
        default=False,
        description="Retract this previously emitted identity; false restores or updates it.",
    )
    kind: Literal["message"] = Field(
        default="message", description="Common event discriminator."
    )
    message_id: str = Field(min_length=1, description="Stable source message identity.")
    thread_id: str = Field(
        min_length=1, description="Native conversation identity, not authorization."
    )
    role: Literal["user", "assistant"] = Field(description="Observed message role.")
    text: str = Field(
        description="Full text so far; replaces the previous version, never a delta."
    )


class ToolCallActivity(BaseModel):
    """Replacement invocation metadata for one thread-scoped tool call."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    removed: bool = Field(
        default=False,
        description="Retract this previously emitted identity; false restores or updates it.",
    )
    kind: Literal["tool_call"] = Field(
        default="tool_call", description="Common event discriminator."
    )
    tool_call_id: str = Field(
        min_length=1, description="Stable call identity within the thread."
    )
    thread_id: str = Field(
        min_length=1, description="Native conversation containing the call."
    )
    name: str = Field(
        min_length=1, description="Reported tool name or observed operation type."
    )
    arguments: dict[str, JsonValue] = Field(
        description="Observed JSON arguments, not instructions to execute."
    )


class ToolResultActivity(BaseModel):
    """Full observed tool output, including running partial output replacements."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    removed: bool = Field(
        default=False,
        description="Retract this previously emitted identity; false restores or updates it.",
    )
    kind: Literal["tool_result"] = Field(
        default="tool_result", description="Common event discriminator."
    )
    tool_call_id: str = Field(
        min_length=1, description="Call identity matching ToolCallActivity."
    )
    thread_id: str = Field(
        min_length=1, description="Thread scope prevents collisions between call IDs."
    )
    status: Literal["running", "completed", "failed", "cancelled", "unknown"] = Field(
        description="Observed tool outcome; running permits incremental output."
    )
    output: str | None = Field(
        description="Full output so far; null means unobserved, not empty."
    )


class UsageActivity(BaseModel):
    """Absolute attempt-to-date per-thread counters; revisions must never be summed."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    removed: bool = Field(
        default=False,
        description="Retract this previously emitted identity; false restores or updates it.",
    )
    kind: Literal["usage"] = Field(
        default="usage", description="Common event discriminator."
    )
    thread_id: str = Field(
        min_length=1,
        description="Native thread to which these exclusive counters belong.",
    )
    input_tokens: int | None = Field(
        ge=0, description="Observed attempt input tokens, or unknown."
    )
    output_tokens: int | None = Field(
        ge=0, description="Observed attempt output tokens, or unknown."
    )
    cached_input_tokens: int | None = Field(
        ge=0, description="Observed cached input category, or unknown."
    )
    reasoning_output_tokens: int | None = Field(
        ge=0, description="Observed reasoning output category, or unknown."
    )
    cache_write_input_tokens: int | None = Field(
        ge=0, description="Observed cache write category, or unknown."
    )
    total_tokens: int | None = Field(
        ge=0,
        description="Reported attempt total, not a sum of potentially overlapping categories.",
    )


class ActivityRecord(BaseModel):
    """One immutable normalized version in an attempt-scoped stable sequence."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    sequence: int = Field(
        gt=0, description="Append-only position within this run/attempt."
    )
    occurred_at: datetime | None = Field(
        description="Provider occurrence time when separately attested; otherwise null."
    )
    observed_at: datetime = Field(
        description="Time this normalized version was observed."
    )
    event: Annotated[
        MessageActivity | ToolCallActivity | ToolResultActivity | UsageActivity,
        Field(discriminator="kind"),
    ] = Field(
        description="Common replacement snapshot; no provider parsing required by the consumer."
    )


class ActivityPage(BaseModel):
    """Bounded normalized records plus the shared display view at a published revision."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    run_id: str = Field(description="Admitted durable runner run identity.")
    attempt_id: str = Field(
        description="Explicit capture identity; never guessed from the latest run."
    )
    available: bool = Field(description="Whether this exact capture boundary exists.")
    records: list[ActivityRecord] = Field(
        description="Increasing records strictly after the requested sequence."
    )
    next_after: int = Field(
        ge=0, description="Continuation position in the normalized sequence."
    )
    has_more: bool = Field(
        description="Additional normalized records exist after this page."
    )
    closed: bool = Field(
        description="Both physical source bounds are sealed, independently of task success."
    )
    complete: bool | None = Field(
        description="Final capture completeness; null while open or unavailable."
    )
    reason: str | None = Field(
        description="Stable unavailability or incomplete-capture category."
    )
    projection: ActivityProjection | None = Field(
        default=None,
        description="Shared display snapshot preserving threads, telemetry, diagnostics and cost.",
    )
    projection_revision: int = Field(
        default=0,
        ge=0,
        description="Monotonic display revision, including changes without new message records.",
    )
    status: str | None = Field(
        default=None,
        description="Selected capture's execution status; not inferred from closure.",
    )
    thread_id: str | None = Field(
        default=None, description="Observed root native thread binding."
    )
    model: str | None = Field(
        default=None, description="Observed effective model binding."
    )
    ended_at: str | None = Field(
        default=None, description="Observed capture end time when present."
    )

    @model_validator(mode="after")
    def consistent_page(self):
        """Reject fabricated closure and malformed normalized ordering."""
        positions = [row.sequence for row in self.records]
        if positions != sorted(set(positions)) or (
            positions and self.next_after != positions[-1]
        ):
            raise ValueError("invalid_activity_cursor")
        if self.has_more and not positions:
            raise ValueError("invalid_activity_cursor")
        if not self.available and (
            self.records or self.closed or self.complete is not None or self.has_more
        ):
            raise ValueError("activity_attempt_identity_mismatch")
        if self.closed != (self.complete is not None):
            raise ValueError("activity_attempt_identity_mismatch")
        if self.projection is not None and (
            not self.available or self.projection_revision < 1
        ):
            raise ValueError("activity_projection_not_available")
        if self.complete is False and not self.reason:
            raise ValueError("activity_capture_reason_required")
        return self

    def to_payload(self) -> dict:
        """Serialize the display view through its explicit omission-preserving boundary."""
        value = self.model_dump(mode="json", exclude={"projection"})
        value["projection"] = (
            self.projection.to_payload() if self.projection is not None else None
        )
        return value
