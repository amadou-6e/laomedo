"""Typed requests inside host orchestration, with explicit component boundaries."""

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from typing import Annotated, Literal


class PrecheckEvidence(BaseModel):
    """Observed precheck evidence; never coerce missing/invalid values into success."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    installed: bool | Literal["unknown"] = Field(
        description="Exact observed boolean, otherwise unknown."
    )
    call_count: Annotated[int, Field(ge=0)] | Literal["unknown"] = Field(
        description="Exact nonnegative observed integer, otherwise unknown."
    )

    @classmethod
    def from_result(cls, value: JsonValue) -> "PrecheckEvidence":
        """Preserve the presenter's exact bool/int tests, excluding bool counts."""
        value = value if isinstance(value, dict) else {}
        installed, count = value.get("installed"), value.get("call_count")
        return cls(
            installed=installed if type(installed) is bool else "unknown",
            call_count=count if type(count) is int and count >= 0 else "unknown",
        )


class AgentRunReference(BaseModel):
    """Graph reference, preserving legacy observational JSON without new admission.

    Passthrough observations deliberately use JsonValue. The presenter cannot
    reject a historical run merely because its evidence predates a typed writer.
    """

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    answer: JsonValue = Field(
        description="Retained answer observation; never parsed or promoted here."
    )
    run_id: JsonValue = Field(description="Previously admitted run identity.")
    request_id: JsonValue = Field(description="Existing client request correlation.")
    invocation_id: JsonValue = Field(description="Existing invocation correlation.")
    laomedo_run_id: JsonValue = Field(
        description="Existing graph-owned run correlation."
    )
    trace_id: JsonValue = Field(description="Safe existing trace identity.")
    evidence_complete: bool | Literal["unknown"] = Field(
        description="Exact completion evidence boolean or unknown."
    )
    completion_basis: JsonValue = Field(
        description="Existing explanation of retained completion evidence."
    )
    requirements_revision: JsonValue = Field(
        description="Pinned output requirements revision observation."
    )
    precheck: PrecheckEvidence = Field(
        description="Normalized precheck evidence, independent of provider completion."
    )
    provider: JsonValue = Field(
        description="Observed provider or the node's existing provider fallback."
    )
    handoff: JsonValue = Field(
        description="Unversioned retained coordination evidence; not new authority."
    )
    imported_artifacts: JsonValue = Field(
        description="Retained artifact observations, including legacy extensions/nulls."
    )
    thread_id: JsonValue = Field(
        description="Existing native conversation observation."
    )
    status: JsonValue = Field(
        description="Observed execution state, without inferred success."
    )
    post_run_hash: JsonValue = Field(
        description="Existing final working-state observation."
    )
    model: JsonValue = Field(description="Requested native model observation.")
    effort: JsonValue = Field(description="Requested native reasoning observation.")
    skill_revision: JsonValue = Field(
        description="Legacy single-skill revision observation."
    )
    skill_use_evidence: JsonValue = Field(
        description="Existing offered/used/unknown observation; preserve legacy values."
    )
    skills: JsonValue = Field(
        description="Retained skill evidence, preserving provider-specific fields and historical shapes."
    )
    artifact_ref: JsonValue = Field(
        description="Existing safe output artifact reference."
    )
    trace_ref: JsonValue = Field(
        description="Existing raw-event reference, never raw transcript contents."
    )
    error_category: JsonValue = Field(
        description="Existing error code; routing remains component-owned."
    )
    attempt_finished: JsonValue = Field(
        description="Existing terminal-attempt observation or false when absent."
    )
    snapshot_ready: JsonValue = Field(
        description="Existing snapshot observation or false when absent."
    )
    cancel_requested: JsonValue = Field(
        description="Existing cancellation-request observation, not confirmation."
    )
    usage: dict[str, JsonValue] | Literal["unknown"] = Field(
        description="Observed usage map, otherwise explicit unknown."
    )

    @classmethod
    def from_runner_status(cls, result: dict, *, provider: str) -> "AgentRunReference":
        """Apply exactly the established graph projection and unknown normalization."""
        skill = result.get("skill") or {}
        return cls(
            answer=result.get("answer"),
            run_id=result["run_id"],
            request_id=result.get("client_request_id"),
            invocation_id=result.get("invocation_id"),
            laomedo_run_id=result.get("laomedo_run_id"),
            trace_id=result.get("trace_id"),
            evidence_complete=(
                result.get("evidence_complete")
                if type(result.get("evidence_complete")) is bool
                else "unknown"
            ),
            completion_basis=result.get("completion_basis"),
            requirements_revision=result.get("requirements_revision"),
            precheck=PrecheckEvidence.from_result(result.get("precheck")),
            provider=result.get("provider") or provider,
            handoff=result.get("handoff"),
            imported_artifacts=result.get("imported_artifacts", []),
            thread_id=result.get("thread_id"),
            status=result.get("status"),
            post_run_hash=result.get("post_run_hash"),
            model=result.get("requested_model"),
            effort=result.get("requested_effort"),
            skill_revision=skill.get("revision_id"),
            skill_use_evidence=skill.get("use_evidence", "unknown"),
            skills=result.get("skills") or ([skill] if skill else []),
            artifact_ref=result.get("output_ref"),
            trace_ref=result.get("raw_event_ref"),
            error_category=result.get("error_category"),
            attempt_finished=result.get("attempt_finished", False),
            snapshot_ready=result.get("snapshot_ready", False),
            cancel_requested=result.get("cancel_requested", False),
            usage=(
                result.get("usage")
                if isinstance(result.get("usage"), dict)
                else "unknown"
            ),
        )

    def to_payload(self) -> dict:
        """Return exactly the graph reference contract, including nulls and unknowns."""
        return self.model_dump()


class RunnerStatusRecord(BaseModel):
    """Join status wire record; intentionally distinct from the graph reference."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    client_request_id: JsonValue = Field(
        default=None, description="Existing runner request correlation."
    )
    request_hash: JsonValue = Field(
        default=None, description="Existing canonical runner request identity."
    )
    run_id: JsonValue = Field(default=None, description="Bound native runner identity.")
    laomedo_run_id: JsonValue = Field(
        default=None, description="Graph-owned run identity."
    )
    trace_id: JsonValue = Field(
        default=None, description="Existing safe trace correlation."
    )
    invocation_id: JsonValue = Field(
        default=None, description="Existing invocation correlation."
    )
    provider: JsonValue = Field(
        default=None, description="Runner provider or configured controller fallback."
    )
    raw_event_ref: JsonValue = Field(
        default=None, description="Safe event reference, never event contents."
    )
    status: JsonValue = Field(
        description="Observed status; unconfirmed cancellation remains incomplete."
    )
    native_status: JsonValue = Field(
        default=None, description="Original native state, retained independently."
    )
    cancel_requested: JsonValue = Field(
        default=None, description="Existing request observation."
    )
    cancel_confirmed: JsonValue = Field(
        default=None, description="Existing confirmation observation."
    )
    executing_graph_verified: Literal[False] = Field(
        default=False, description="The status bridge does not certify graph execution."
    )
    answer: JsonValue = Field(
        default=None, description="Existing native answer observation."
    )
    activity_initial_attempt_id: JsonValue = Field(
        default=None, description="Initial activity capture identity."
    )
    activity_attempt_id: JsonValue = Field(
        default=None, description="Current native activity attempt identity."
    )
    attempt_finished: JsonValue = Field(
        default=None, description="Native terminal-attempt observation."
    )
    snapshot_ready: JsonValue = Field(
        default=None, description="Native final-snapshot observation."
    )
    thread_id: JsonValue = Field(
        default=None, description="Native conversation observation."
    )
    post_run_hash: JsonValue = Field(
        default=None, description="Native final working-state observation."
    )
    requested_model: JsonValue = Field(
        default=None, description="Native requested model observation."
    )
    requested_effort: JsonValue = Field(
        default=None, description="Native requested effort observation."
    )
    skill: JsonValue = Field(
        default=None, description="Legacy single-skill observation."
    )
    skills: JsonValue = Field(
        default=None, description="Retained native skill observations."
    )
    output_ref: JsonValue = Field(
        default=None, description="Existing safe output artifact reference."
    )
    handoff: JsonValue = Field(
        default=None, description="Retained coordination evidence."
    )
    imported_artifacts: JsonValue = Field(
        default=None, description="Retained imported artifact evidence."
    )
    usage: JsonValue = Field(
        default=None, description="Native usage observation without inferred defaults."
    )
    error_category: JsonValue = Field(
        default=None, description="Existing safe native failure code."
    )

    @classmethod
    def from_snapshot(
        cls, snapshot: dict | None, *, provider: str
    ) -> "RunnerStatusRecord":
        """Project a join snapshot without validating its historical native record."""
        if snapshot is None:
            return cls(status="pending_start")
        native = snapshot.get("native_record") or {}
        return cls(
            client_request_id=snapshot["client_request_id"],
            request_hash=snapshot["runner_request_hash"],
            run_id=snapshot["runner_run_id"],
            laomedo_run_id=snapshot["run_id"],
            trace_id=snapshot["trace_id"],
            invocation_id=snapshot["invocation_id"],
            provider=snapshot["runner_provider"] or provider,
            raw_event_ref=snapshot["runner_raw_event_ref"],
            status=(
                "incomplete"
                if snapshot.get("native_status") == "cancelled"
                and snapshot.get("cancel_confirmed") is not True
                else snapshot.get("native_status") or snapshot["status"]
            ),
            native_status=snapshot.get("native_status"),
            cancel_requested=snapshot.get("cancel_requested", False),
            cancel_confirmed=snapshot.get("cancel_confirmed", False),
            executing_graph_verified=False,
            answer=native.get("answer"),
            activity_initial_attempt_id=native.get("activity_initial_attempt_id"),
            activity_attempt_id=native.get("activity_attempt_id"),
            attempt_finished=native.get("attempt_finished", False),
            snapshot_ready=native.get("snapshot_ready", False),
            thread_id=native.get("thread_id"),
            post_run_hash=native.get("post_run_hash"),
            requested_model=native.get("requested_model"),
            requested_effort=native.get("requested_effort"),
            skill=native.get("skill"),
            skills=native.get("skills"),
            output_ref=native.get("output_ref"),
            handoff=native.get("handoff"),
            imported_artifacts=native.get("imported_artifacts", []),
            usage=native.get("usage"),
            error_category=native.get("error_category"),
        )

    def to_payload(self) -> dict:
        """Pending output has only status; populated snapshots retain every old key."""
        return self.model_dump(exclude_unset=True)


class AgentDispatchResult(BaseModel):
    """The bridge's safe result allowlist, excluding profile, auth and host paths."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    provider: str = Field(description="Provider selected by the admitted handoff.")
    run_id: JsonValue = Field(description="Previously admitted native run identity.")
    thread_id: JsonValue = Field(description="Native conversation observation.")
    status: JsonValue = Field(description="Native execution observation.")
    answer: JsonValue = Field(description="Native answer observation.")
    post_run_hash: JsonValue = Field(
        description="Native final working-state observation."
    )
    model: JsonValue = Field(description="Requested model observation.")
    effort: JsonValue = Field(description="Requested effort observation.")
    skills: JsonValue = Field(description="Retained native skill evidence.")
    error_category: JsonValue = Field(
        description="Existing safe native error category."
    )

    @classmethod
    def from_result(cls, raw: dict, *, provider: str) -> "AgentDispatchResult":
        """Project only the established allowlisted native result fields."""
        return cls(
            provider=provider,
            run_id=raw["run_id"],
            thread_id=raw.get("thread_id"),
            status=raw.get("status"),
            answer=raw.get("answer"),
            post_run_hash=raw.get("post_run_hash"),
            model=raw.get("requested_model"),
            effort=raw.get("requested_effort"),
            skills=raw.get("skills"),
            error_category=raw.get("error_category"),
        )

    def to_payload(self) -> dict:
        """Return the existing bridge result shape, with no new fields."""
        return self.model_dump()


class AgentSubmission(BaseModel):
    """Final routed graph submission after the component's existing safety checks."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    schema_version: Literal["laomedo.agent-submission.v1"] = Field(
        default="laomedo.agent-submission.v1",
        description="Existing graph submission schema.",
    )
    submission: dict[str, JsonValue] | None = Field(
        description="Parsed JSON-object answer when available, otherwise null."
    )
    answer: JsonValue = Field(description="Unmodified retained answer observation.")
    requirements_revision: JsonValue = Field(
        description="Existing pinned output requirement observation."
    )
    precheck: JsonValue = Field(
        description="Existing normalized precheck or explicit unknown default."
    )
    task_outcome: Literal["success", "failure", "unknown"] = Field(
        description="Routed outcome after rejecting unconfirmed success."
    )
    executor_status: JsonValue = Field(
        description="Observed native state, falling back to unknown."
    )
    evidence_complete: JsonValue = Field(
        description="Existing completion evidence, not inferred from a graph build."
    )
    run_reference: dict[str, JsonValue] = Field(
        description="Existing full or partial routed run reference, preserving its error path shape."
    )
    error_category: JsonValue = Field(description="Already routed safe error category.")

    def to_payload(self) -> dict:
        """Preserve the existing submission boundary and explicit null values."""
        return self.model_dump()


class AgentRequest(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    endpoint: str = Field(
        description="Admitted local runner endpoint for this operation."
    )
    payload: dict | None = Field(
        repr=False,
        description="Existing wire request body, or no body for a read operation.",
    )
    method: str = Field(
        description="HTTP method associated with the prepared operation."
    )

    @classmethod
    def from_component_request(cls, prepared):
        endpoint, payload, method = prepared
        return cls(endpoint=endpoint, payload=payload, method=method)

    def with_activity_attempt(self, invocation_id):
        return type(self)(
            endpoint=self.endpoint,
            payload={**self.payload, "activity_attempt_id": invocation_id},
            method=self.method,
        )

    def component_arguments(self):
        """Saved components retain their existing _http(endpoint, payload, method) API."""
        return self.endpoint, self.payload, self.method


# Closed external handoff/artifact vocabulary, not provider selection logic.
SUPPORTED_PROVIDERS = frozenset({"codex", "opencode", "claude"})
