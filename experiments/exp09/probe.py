"""EXP-09: retain raw deliveries while exposing uncertain action identity."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from experiments.exp05.evidence import EvidenceStore
from laomedo.workflow_run_store import WorkflowRunStore


def _digest(payload_json: str) -> str:
    return "sha256:" + hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _new_case(path: Path) -> tuple[EvidenceStore, str, str]:
    runs = WorkflowRunStore(path)
    store = EvidenceStore(path)
    run = runs.reserve(
        graph={"nodes": [{"id": "stage"}]},
        component_code={"stage": "synthetic-exp09"},
        resolved_config={"model": "none"},
        trigger={"type": "direct"},
    )
    invocation = "invocation-1"
    store.reserve(
        run_id=run["run_id"], trace_id=run["trace_id"],
        stage_id="stage", invocation_id=invocation,
    )
    store.record_native_session(invocation, "synthetic-session")
    return store, run["run_id"], run["trace_id"]


def _append(store: EvidenceStore, invocation: str, source_id: str | None,
            kind: str, summary: str, call_id: str | None = None) -> None:
    payload = {"summary": summary}
    if call_id is not None:
        payload["call_id"] = call_id
    store.append_raw_event(
        invocation, source_event_id=source_id, kind=kind, payload=payload,
    )


def _project(store: EvidenceStore, invocation: str) -> dict:
    """Build a receipt-backed read model, never a unique-native-action model."""
    store.project_unprojected()
    snapshot = store.inspect()
    raw = [row for row in snapshot["raw_events"]
           if row["invocation_id"] == invocation]
    projected = {row["receipt_sequence"]: row
                 for row in snapshot["projections"]
                 if row["invocation_id"] == invocation}
    if len(raw) != len(projected) or any(
            row["receipt_sequence"] not in projected for row in raw):
        raise AssertionError("raw receipt/projection mismatch")
    status = next(row["stream_state"] for row in snapshot["invocations"]
                  if row["invocation_id"] == invocation)
    events = [{
        "receipt_sequence": row["receipt_sequence"],
        "source_event_id": row["source_event_id"],
        "kind": row["kind"],
        "payload_sha256": _digest(row["payload_json"]),
        "summary": projected[row["receipt_sequence"]]["summary"],
        "action_uniqueness": "uncertain",
    } for row in raw]
    return {
        "delivery_count": len(events),
        "action_uniqueness": "uncertain",
        "unique_action_count": None,
        "stream_state": status,
        "events": events,
    }


def _read_twice(store: EvidenceStore, invocation: str) -> dict:
    before = store.inspect()["raw_events"]
    first = _project(store, invocation)
    projected_before = store.inspect()["projections"]
    again = _project(store, invocation)
    if (first != again or
            store.inspect()["projections"] != projected_before or
            store.inspect()["raw_events"] != before):
        raise AssertionError("reprojection changed evidence")
    return first


def run_cases(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)

    path = root / "reconnect.sqlite3"
    store, _, _ = _new_case(path)
    _append(store, "invocation-1", "evt-1", "message", "arrived")
    store = EvidenceStore(path)  # A new client sees the same durable receipt log.
    _append(store, "invocation-1", "evt-1", "message", "arrived")
    store.mark_complete("invocation-1")
    reconnect = _read_twice(store, "invocation-1")

    store, _, _ = _new_case(root / "conflict.sqlite3")
    _append(store, "invocation-1", "evt-2", "message", "first payload")
    _append(store, "invocation-1", "evt-2", "message", "changed payload")
    store.mark_complete("invocation-1")
    conflict = _read_twice(store, "invocation-1")

    store, _, _ = _new_case(root / "keyless.sqlite3")
    _append(store, "invocation-1", None, "tool_result", "result first", "call-1")
    _append(store, "invocation-1", None, "tool_call", "call later", "call-1")
    _append(store, "invocation-1", None, "tool_result", "result first", "call-1")
    store.sweep_crashed()
    keyless = _read_twice(store, "invocation-1")

    store, run_id, trace_id = _new_case(root / "invocations.sqlite3")
    store.reserve(
        run_id=run_id, trace_id=trace_id, stage_id="stage",
        invocation_id="invocation-2",
    )
    store.record_native_session("invocation-2", "synthetic-session")
    _append(store, "invocation-1", "shared", "tool_call", "start", "call-2")
    _append(store, "invocation-2", "shared", "tool_result", "finish", "call-2")
    store.mark_complete("invocation-1")
    store.mark_complete("invocation-2")
    separate = {
        "invocation_1": _read_twice(store, "invocation-1"),
        "invocation_2": _read_twice(store, "invocation-2"),
    }

    return {
        "policy": "at_least_once_uncertain",
        "source": "synthetic EXP-05 SQLite ingestion and receipt projection",
        "reconnect_replay": reconnect,
        "conflicting_source_id": conflict,
        "keyless_reordered": keyless,
        "separate_invocations": separate,
    }


def main(output_path: Path | None = None) -> dict:
    with TemporaryDirectory(prefix="laomedo-exp09-") as temp:
        observation = run_cases(Path(temp))
    if output_path is not None:
        with output_path.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(observation, stream, indent=2)
            stream.write("\n")
        print(output_path)
    return observation


if __name__ == "__main__":
    if sys.argv[1:] == ["--record"]:
        main(Path(__file__).with_name("observation.json"))
    elif len(sys.argv) == 1:
        main()
        print("EXP-09: synthetic at-least-once replay cases passed")
    else:
        raise SystemExit("usage: python -m experiments.exp09.probe [--record]")
