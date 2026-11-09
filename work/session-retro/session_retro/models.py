"""Typed source identities, locators, decoded observations and coverage values."""

from typing import Literal

from pydantic import BaseModel, Field


class SourceSnapshot(BaseModel):
    """A finite input boundary and its transactionally committed verified prefix."""

    path: str = Field(description="Absolute private source file path")
    session_id: str = Field(description="Expected native session_meta identity")
    identity: str = Field(description="Filesystem device and file identity")
    boundary: int = Field(ge=0, description="Finite source byte length admitted")
    indexed_bytes: int = Field(
        default=0, ge=0, description="End of committed complete records"
    )
    lines: int = Field(default=0, ge=0, description="Committed physical JSONL records")
    sha256: str = Field(description="SHA256 of committed complete source prefix")
    complete: bool = Field(
        default=False, description="Captured boundary scanned and prefix reverified"
    )
    trailing_bytes: int = Field(
        default=0, ge=0, description="Incomplete final record bytes, not decoded"
    )
    parser_version: str = Field(description="Decoder and index contract version")
    settings_digest: str = Field(description="Hash of interpretation-affecting limits")


class RecordLocator(BaseModel):
    """Exact original byte range; hash verifies later evidence reads."""

    line: int = Field(ge=1, description="One-based physical source line")
    offset: int = Field(
        ge=0, description="Zero-based byte offset, not character offset"
    )
    length: int = Field(ge=1, description="Record bytes including terminating newline")
    sha256: str = Field(description="SHA256 of exact original record bytes")
    prefix_sha256: str = Field(description="SHA256 through this complete record")


class SourceRecord(BaseModel):
    """One bounded native record; oversized data is retained only by locator."""

    locator: RecordLocator = Field(description="Original source range and integrity")
    data: bytes | None = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Bounded native bytes or None when oversized",
    )


class NormalizedEvent(BaseModel):
    """Observed event metadata, never a claim that the task succeeded."""

    locator: RecordLocator = Field(description="Original physical record identity")
    timestamp: str | None = Field(
        default=None, description="Native timestamp, unmodified"
    )
    native_type: str = Field(description="Outer type and optional native payload type")
    kind: str = Field(
        description="Message, call, result, compaction, observation or explicit gap"
    )
    role: str | None = Field(default=None, description="Observed speaker if supplied")
    phase: str | None = Field(
        default=None,
        description="Native commentary/final-answer channel; not inferred from text",
    )
    message_id: str | None = Field(
        default=None, description="Native item identity for duplicate investigation"
    )
    call_id: str | None = Field(
        default=None, description="Native tool correlation ID when present"
    )
    turn_id: str | None = Field(
        default=None,
        description="Explicit or latest carried native turn ID; not necessarily supplied by this record",
    )
    name: str | None = Field(
        default=None, description="Native tool or observation name"
    )
    failure: bool | None = Field(
        default=None, description="Explicit known failure; None means unknown"
    )
    text: str = Field(
        default="", repr=False, description="Bounded best-effort-redacted search value"
    )
    text_truncated: bool = Field(
        default=False, description="Search value omits native text"
    )


class BuildResult(BaseModel):
    """Observed execution and input integrity metrics for one indexing invocation."""

    snapshot: SourceSnapshot = Field(description="Committed source boundary")
    elapsed_seconds: float = Field(description="Measured invocation elapsed wall time")
    peak_rss_bytes: int = Field(
        description="Peak resident memory of this single-process CLI"
    )


class ReadPage(BaseModel):
    """Source-derived normalized text page, with explicit continuation."""

    line: int = Field(description="Original source line verified against its hash")
    native_type: str = Field(description="Native record type")
    text: str = Field(description="Best-effort-redacted extracted text page")
    start: int = Field(description="Character offset in extracted text")
    next_start: int | None = Field(
        default=None, description="Next character offset or None"
    )
    total_characters: int = Field(description="Extracted text length before paging")
    redaction: str = Field(
        default="best_effort_private_only",
        description="No guarantee of safe publication",
    )


class CoverageReport(BaseModel):
    """Physical indexing and interpretation coverage, explicitly not analysis."""

    snapshot: SourceSnapshot = Field(description="Stable source and indexed prefix")
    records: int = Field(description="Indexed physical JSONL records")
    kinds: dict[str, int] = Field(description="Normalized categories including gaps")
    types: dict[str, int] = Field(description="Native outer and payload type counts")
    paired_call_ids: int = Field(description="Exactly one call and one result per ID")
    ambiguous_or_unpaired_call_ids: int = Field(
        description="IDs with missing or multiple call/results"
    )
    calls_without_id: int = Field(
        description="Call/result records without correlation identity"
    )
    explicit_failure_records: int = Field(
        description="Records containing recognized explicit failure status"
    )
    result_outcomes_unknown: int = Field(
        description="Result records without a recognized explicit terminal signal"
    )
    usage_values: str = Field(
        default="source_only_not_aggregated",
        description="Usage records are located, not summed into unsupported cost claims",
    )
    truncated_search_records: int = Field(
        description="Records whose search values omit text"
    )
    analyzed_records: int = Field(
        default=0, description="Indexing itself performs no retrospective analysis"
    )
    omitted_native_types: int = Field(
        default=0,
        description="Additional distinct native types omitted from bounded histogram",
    )
    search_coverage: str = Field(
        default="bounded_extracted_text_only",
        description="Search completeness limitation",
    )
    child_sources: str = Field(
        default="not_opened",
        description="Referenced children are outside selected source",
    )


class SearchHit(BaseModel):
    """A bounded search match that must be checked against original context."""

    line: int = Field(description="Physical source line")
    timestamp: str | None = Field(description="Original timestamp when available")
    kind: str = Field(description="Decoded category")
    role: str | None = Field(description="Observed speaker")
    phase: str | None = Field(description="Native message phase when supplied")
    name: str | None = Field(description="Observed tool or event name")
    call_id: str | None = Field(description="Observed correlation identity")
    offset: int = Field(description="Original byte offset")
    length: int = Field(description="Original byte length")
    text: str = Field(
        repr=False, description="Bounded best-effort-redacted search text"
    )
    text_truncated: bool = Field(description="Further source text exists")


class VerificationResult(BaseModel):
    """Exact committed prefix verified without interpreting source content."""

    verified: bool = Field(description="Prefix identity and hash matched")
    bytes: int = Field(description="Verified committed prefix length")
    sha256: str = Field(description="Verified prefix hash")


class ReportResult(BaseModel):
    """Private candidate report locations, not a confirmed incident verdict."""

    directory: str = Field(description="Private report directory")
    episodes: int = Field(
        default=0, description="User-message windows, not distinct tasks"
    )
    messages: int = Field(
        description="Message observations written, not deduplicated requests"
    )
    candidates: int = Field(
        description="Candidate review locations, not confirmed mistakes"
    )
    status: str = Field(
        default="candidate_queue_requires_source_review",
        description="Analytical limitation",
    )


class Episode(BaseModel):
    """A physical user-message window; task continuity needs semantic review."""

    id: str = Field(
        description="Stable window identifier derived from original user line"
    )
    source_kind: Literal[
        "request_or_continuation", "clarification", "injected_context"
    ] = Field(
        default="request_or_continuation",
        description="Native user records can contain injected context rather than human requests",
    )
    start_line: int = Field(description="Original user-message source line")
    end_line: int = Field(description="Last physical line before the next user message")
    turn_id: str | None = Field(
        description="Attributed user turn; may be carried from the latest observed turn ID"
    )
    user_text: str = Field(description="Private redacted bounded original request text")
    user_text_truncated: bool = Field(
        description="Original user text needs further source pages"
    )
    final_answer_lines: list[int] = Field(
        default_factory=list, description="Original final-answer source locations"
    )
    omitted_final_answer_lines: int = Field(
        default=0,
        description="Further final-answer locations omitted from this bounded window summary",
    )
    calls: int = Field(default=0, description="Observed calls in the window")
    results: int = Field(default=0, description="Observed results in the window")
    explicit_failure_records: int = Field(
        default=0, description="Tool failures, not automatically agent mistakes"
    )
    compactions: int = Field(default=0, description="Compactions inside this window")


class EvidenceReference(BaseModel):
    """A statement grounded in original immutable-prefix record locations."""

    lines: list[int] = Field(
        description="Original physical lines supporting this evidence"
    )
    statement: str = Field(
        description="Concise observation, distinct from causal inference"
    )
    relation: Literal[
        "intent", "action", "result", "claim", "correction", "counterevidence"
    ] = Field(description="Role of the observation in the incident")


class Incident(BaseModel):
    """Reviewed behavior discrepancy with uncertainty and counterevidence retained."""

    id: str = Field(
        description="Stable incident identity; compaction repeats do not add recurrence"
    )
    title: str = Field(description="Concrete observed problem")
    category: str = Field(description="Behavioral concern, not a blame label")
    severity: str = Field(description="Impact assessment and priority")
    summary: str = Field(description="Requested versus observed behavior")
    evidence: list[EvidenceReference] = Field(
        description="Original supporting and counterevidence references"
    )
    causal_status: Literal["observed", "inferred", "unresolved"] = Field(
        description="Confidence category for the proposed mechanism"
    )
    mechanism: str = Field(
        description="Evidence-bounded explanation and remaining uncertainty"
    )
    source_sha256: str = Field(description="Exact immutable source prefix reviewed")
    status: Literal["candidate", "source_reviewed", "independently_checked"] = Field(
        description="Review status, distinct from prevention effectiveness"
    )


class PreventionProposal(BaseModel):
    """Unapplied change with a falsifiable recurrence-prevention check."""

    id: str = Field(description="Stable proposal identity")
    incident_ids: list[str] = Field(
        description="Distinct source-reviewed incidents motivating it"
    )
    owner: str = Field(description="Owning repository, skill or concern")
    proposed_change: str = Field(
        description="Smallest concrete change, not automatically applied"
    )
    verification: str = Field(
        description="Fail-before/pass-after or representative scenario evaluation"
    )
    false_positive_check: str = Field(
        description="Compliant behavior that must still be allowed"
    )
    status: Literal["proposed", "approved", "applied", "verified"] = Field(
        default="proposed",
        description="Approval/application/effectiveness are separate states",
    )


class OperationFailure(BaseModel):
    """Safe explanation and inspection-oriented recovery for failed evidence work."""

    code: str = Field(description="Stable machine-readable local error category")
    message: str = Field(description="Known plain-language failure explanation")
    recovery: str = Field(
        default="Check the selected source, output path and coverage. For changed evidence or parser settings, preserve the old index and create a new one; do not silently trust stale results.",
        description="Recovery that does not mutate original evidence",
    )
