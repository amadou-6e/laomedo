"""Crash-window probe for the durable synthetic dispatch reservation."""

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from laomedo.workflow_run_store import WorkflowRunStore  # noqa: E402


FLOW = ROOT / "experiments" / "exp03" / "flow.json"


def launch(store):
    graph = json.loads(FLOW.read_text(encoding="utf-8"))["data"]
    marker = next(n for n in graph["nodes"] if n["id"] == "Exp03Marker-exp03")
    code = marker["data"]["node"]["template"]["code"]["value"]
    return store.reserve(graph=graph, component_code={marker["id"]: code},
                         resolved_config={"marker": "BEFORE", "mode": "synthetic"},
                         trigger={"type": "direct", "task": "TASK"})


def child(phase, database):
    store = WorkflowRunStore(database)
    if phase == "before_write":
        os._exit(11)
    record = launch(store)
    if phase == "after_write_before_ack":
        os._exit(12)
    print(json.dumps({"run_id": record["run_id"], "trace_id": record["trace_id"]}), flush=True)
    if phase == "after_ack_before_dispatch":
        os._exit(13)
    if phase == "after_attempt_before_callback":
        store.dispatch(record["run_id"], lambda _: os._exit(14))
    if phase == "after_callback_before_completion":
        def callback(run_id):
            store.record_synthetic_dispatch(run_id)
            os._exit(15)
        store.dispatch(record["run_id"], callback)
    result = store.dispatch(record["run_id"], store.record_synthetic_dispatch)
    print(json.dumps({"synthetic_sequence": result}), flush=True)


def parent():
    observations = {}
    with TemporaryDirectory(prefix="laomedo-exp04-") as root:
        for phase in ("before_write", "after_write_before_ack",
                      "after_ack_before_dispatch", "after_attempt_before_callback",
                      "after_callback_before_completion", "normal"):
            database = Path(root) / phase / "runs.sqlite3"
            process = subprocess.run([sys.executable, str(Path(__file__)), "--child",
                                      phase, str(database)], capture_output=True, text=True,
                                     timeout=20, check=False)
            store = WorkflowRunStore(database)
            with store._database() as db:
                before = [dict(row) for row in db.execute("""SELECT run_id,trace_id,
                    graph_revision,component_revisions,resolved_config_ref,status,
                    dispatch_attempts FROM runs""")]
            counters_before = store.counters()
            swept = store.sweep_crashed()
            with store._database() as db:
                after = [dict(row) for row in db.execute("""SELECT run_id,status,
                    evidence_complete,terminal_reason,dispatch_attempts FROM runs""")]
            observations[phase] = {"exit_code": process.returncode,
                                   "acknowledged": bool(process.stdout.strip()),
                                   "rows_before_restart": before,
                                   "counters_before_restart": counters_before,
                                   "swept_run_ids": swept,
                                   "rows_after_restart": after,
                                   "counters_after_restart": store.counters(),
                                   "stderr": process.stderr[-500:]}
    expected = {
        "before_write": (0, 0, 0, []),
        "after_write_before_ack": (1, 0, 0, ["crashed"]),
        "after_ack_before_dispatch": (1, 0, 0, ["crashed"]),
        "after_attempt_before_callback": (1, 1, 0, ["crashed"]),
        "after_callback_before_completion": (1, 1, 1, ["crashed"]),
        "normal": (1, 1, 1, ["completed"]),
    }
    for phase, (runs, attempts, callbacks, statuses) in expected.items():
        item = observations[phase]
        actual = item["counters_before_restart"]
        if ((actual["runs"], actual["dispatch_attempts"],
             actual["synthetic_dispatches"],
             [row["status"] for row in item["rows_after_restart"]]) !=
                (runs, attempts, callbacks, statuses)):
            raise AssertionError(f"unexpected crash-window result: {phase}")
    output = Path(__file__).with_name("observation.json")
    output.write_text(json.dumps(observations, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--child":
        child(sys.argv[2], sys.argv[3])
    else:
        parent()
