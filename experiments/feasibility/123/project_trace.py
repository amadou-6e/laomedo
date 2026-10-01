"""Credential-free trace projection spike for specs issue #123.

The input is a sanitized, provider-neutral envelope, not a raw provider trace.
Raw payloads remain in private state; their IDs and SHA-256 digests survive here.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any


KINDS = {
    "start", "message", "tool_call", "tool_result", "file_change",
    "skill_access", "approval", "usage", "error", "end",
}
STATUSES = {"completed", "failed", "cancelled", "timed_out", "interrupted"}


@dataclass(frozen=True)
class Envelope:
    source: str
    source_event_id: str | None
    source_time: str | None
    kind: str
    payload_sha256: str
    native_session_id: str | None = None
    tool_call_id: str | None = None
    terminal_status: str | None = None
    usage: dict[str, Any] | None = None
    observed_at: str | None = None
    payload_ref: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError("unsupported event kind")
        if self.terminal_status is not None and self.terminal_status not in STATUSES:
            raise ValueError("unsupported terminal status")
        if len(self.payload_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.payload_sha256):
            raise ValueError("payload digest must be lowercase SHA-256")
        if self.usage is not None:
            for value in self.usage.values():
                if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                    raise ValueError("usage counters must be nonnegative integers or null")


def digest(value: Any) -> str:
    """Hash exact canonical JSON bytes for a synthetic or already sanitized fixture."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def project(run_id: str, envelopes: list[Envelope]) -> dict[str, Any]:
    """Preserve receipt order and unknown values; never infer provider behavior."""
    if not run_id:
        raise ValueError("run_id is required")
    events: list[dict[str, Any]] = []
    seen: dict[tuple[str, str], str] = {}
    duplicates = 0
    for received_ordinal, envelope in enumerate(envelopes):
        if envelope.source_event_id is not None:
            key = (envelope.source, envelope.source_event_id)
            if key in seen and seen[key] != envelope.payload_sha256:
                raise ValueError("source event ID reused with different payload")
            if key in seen:
                duplicates += 1
                continue
            seen[key] = envelope.payload_sha256
        events.append({
            "event_id": f"{run_id}:{len(events)}",
            "run_id": run_id,
            "sequence": len(events),
            "received_ordinal": received_ordinal,
            "source": envelope.source,
            "source_event_id": envelope.source_event_id,
            "source_time": envelope.source_time,
            "observed_at": envelope.observed_at,
            "kind": envelope.kind,
            "payload_ref": envelope.payload_ref,
            "payload_sha256": envelope.payload_sha256,
            "native_session_id": envelope.native_session_id,
            "tool_call_id": envelope.tool_call_id,
            "terminal_status": envelope.terminal_status,
            "usage": dict(envelope.usage) if envelope.usage is not None else None,
            "provenance": "observed",
        })
    calls = {event["tool_call_id"] for event in events if event["kind"] == "tool_call" and event["tool_call_id"]}
    results = {event["tool_call_id"] for event in events if event["kind"] == "tool_result" and event["tool_call_id"]}
    terminal = [event["terminal_status"] for event in events if event["kind"] == "end" and event["terminal_status"]]
    return {
        "schema_version": 1,
        "run_id": run_id,
        "events": events,
        "duplicates_ignored": duplicates,
        "linked_tool_call_ids": sorted(calls & results),
        "unmatched_tool_call_ids": sorted(calls - results),
        "orphan_tool_result_ids": sorted(results - calls),
        "status": terminal[-1] if terminal else "interrupted",
        "trace_complete": bool(terminal),
    }
