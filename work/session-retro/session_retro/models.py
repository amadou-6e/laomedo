"""Typed source identities, locators, decoded observations and coverage values."""

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
    turn_id: str | None = Field(default=None, description="Native turn ID when present")
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
    truncated_search_records: int = Field(
        description="Records whose search values omit text"
    )
    analyzed_records: int = Field(
        default=0, description="Indexing itself performs no retrospective analysis"
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


class OperationFailure(BaseModel):
    """Safe explanation and inspection-oriented recovery for failed evidence work."""

    code: str = Field(description="Stable machine-readable local error category")
    message: str = Field(description="Known plain-language failure explanation")
    recovery: str = Field(
        default="Check the selected source, output path and coverage. For changed evidence or parser settings, preserve the old index and create a new one; do not silently trust stale results.",
        description="Recovery that does not mutate original evidence",
    )
