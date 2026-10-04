"""Process-kill probe for invocation identities and partial raw events."""

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from laomedo.workflow_run_store import WorkflowRunStore  # noqa: E402
from experiments.exp05.evidence import EvidenceStore  # noqa: E402


PHASES = (
    "before_invocation_reserve",
    "after_invocation_reserve",
    "after_dispatch_before_native",
    "after_native_id",
    "after_event_flush",
    "after_projection",
    "normal",
)


def child(phase, database):
    run_store = WorkflowRunStore(database)
    evidence = EvidenceStore(database)
    run = run_store.reserve(
        graph={"nodes": [{"id": "synthetic-provider"}]},
        component_code={"synthetic-provider": "EXP-05 synthetic provider v1"},
        resolved_config={"provider": "synthetic", "mode": "zero-model"},
        trigger={"type": "direct", "task": "EXP-05"},
    )
    if phase == "before_invocation_reserve":
        os._exit(11)
    invocation_id = str(uuid4())
    evidence.reserve(run_id=run["run_id"], trace_id=run["trace_id"],
                     stage_id="synthetic-provider", invocation_id=invocation_id)
    if phase == "after_invocation_reserve":
        os._exit(12)

    def callback(_run_id):
        if phase == "after_dispatch_before_native":
            os._exit(13)
        evidence.record_native_session(invocation_id, "synthetic-session-1")
        if phase == "after_native_id":
            os._exit(14)
        evidence.append_raw_event(
            invocation_id, source_event_id="synthetic-event-1", kind="tool_call",
            payload={"summary": "synthetic read", "tool": "fixture"},
        )
        if phase == "after_event_flush":
            os._exit(15)
        evidence.project_unprojected()
        if phase == "after_projection":
            os._exit(16)
        evidence.mark_complete(invocation_id)
        return "synthetic-complete"

    run_store.dispatch(run["run_id"], callback)


def parent(output_path=None):
    observations = {}
    with TemporaryDirectory(prefix="laomedo-exp05-") as root:
        for phase in PHASES:
            database = Path(root) / phase / "evidence.sqlite3"
            process = subprocess.run(
                [sys.executable, str(Path(__file__)), "--child", phase, str(database)],
                capture_output=True, text=True, timeout=20, check=False,
            )
            run_store = WorkflowRunStore(database)
            evidence = EvidenceStore(database)
            before = evidence.inspect()
            run_rows_before = run_store.counters()
            crashed_invocations = evidence.sweep_crashed()
            crashed_runs = run_store.sweep_crashed()
            after = evidence.inspect()
            run = run_store.get(after["invocations"][0]["run_id"]) if after["invocations"] else None
            observations[phase] = {
                "exit_code": process.returncode,
                "stderr": process.stderr[-500:],
                "run_counters_before_restart": run_rows_before,
                "raw_count_before_restart": len(before["raw_events"]),
                "projection_count_before_restart": len(before["projections"]),
                "invocation_before_restart": before["invocations"],
                "swept_invocation_ids": crashed_invocations,
                "swept_run_ids": crashed_runs,
                "invocation_after_restart": after["invocations"],
                "raw_events_after_restart": after["raw_events"],
                "projections_after_restart": after["projections"],
                "run_after_restart": {
                    key: run[key] for key in
                    ("run_id", "trace_id", "status", "evidence_complete", "dispatch_attempts")
                } if run else None,
            }
    expected = {
        "before_invocation_reserve": (11, 0, 0, 0, 0, False, "crashed", "unknown"),
        "after_invocation_reserve": (12, 1, 0, 0, 0, False, "crashed", "unknown"),
        "after_dispatch_before_native": (13, 1, 1, 0, 0, False, "crashed", "unknown"),
        "after_native_id": (14, 1, 1, 0, 0, True, "crashed", "unknown"),
        "after_event_flush": (15, 1, 1, 1, 0, True, "crashed", "partial"),
        "after_projection": (16, 1, 1, 1, 1, True, "crashed", "partial"),
        "normal": (0, 1, 1, 1, 1, True, "completed", "complete"),
    }
    for phase, (exit_code, invocations, attempts, raw, before_projection,
                native_known, status, stream) in expected.items():
        observation = observations[phase]
        after = observation["invocation_after_restart"]
        actual = (
            observation["exit_code"],
            len(after),
            observation["run_counters_before_restart"]["dispatch_attempts"],
            len(observation["raw_events_after_restart"]),
            observation["projection_count_before_restart"],
            bool(after and after[0]["native_session_id"]),
            after[0]["status"] if after else "crashed",
            after[0]["stream_state"] if after else "unknown",
        )
        if actual != (exit_code, invocations, attempts, raw, before_projection,
                      native_known, status, stream):
            raise AssertionError(f"{phase}: {actual!r}")
        if observation["stderr"]:
            raise AssertionError(f"{phase}: child wrote stderr")
        if len(observation["swept_run_ids"]) != (0 if status == "completed" else 1):
            raise AssertionError(f"{phase}: incorrect run sweep")
        if after:
            item = after[0]
            run = observation["run_after_restart"]
            assert item["run_id"] == run["run_id"]
            assert item["trace_id"] == run["trace_id"]
            assert all(event["invocation_id"] == item["invocation_id"]
                       for event in observation["raw_events_after_restart"])
            raw_ids = [event["receipt_sequence"]
                       for event in observation["raw_events_after_restart"]]
            projected_ids = [event["receipt_sequence"]
                             for event in observation["projections_after_restart"]]
            assert raw_ids == projected_ids
            assert run["status"] == status
        elif observation["run_counters_before_restart"]["runs"] != 1:
            raise AssertionError(f"{phase}: missing reserved run")
        assert (len(observation["swept_invocation_ids"]) == (0 if status == "completed" else invocations))
    if output_path is not None:
        output = Path(output_path)
        with output.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(observations, indent=2) + "\n")
        print(output)
    return observations


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--child":
        child(sys.argv[2], sys.argv[3])
    elif sys.argv[1:] == ["--record"]:
        parent(Path(__file__).with_name("observation.json"))
    elif len(sys.argv) == 1:
        parent()
        print("EXP-05: seven crash/control phases passed")
    else:
        raise SystemExit("usage: probe.py [--record]")
