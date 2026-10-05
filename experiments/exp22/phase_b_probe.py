"""One-shot, capped native-cancellation probe for EXP-22 Phase B.

Private state and raw events stay under --state. This script never publishes
or retries a model request. The committed amendment governs interpretation.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time
from uuid import uuid4

from laomedo.local_runner import AppServer, LocalRunner
from laomedo.skill_store import SkillStore


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "examples/skill-agent-pilot/source"
SKILL = ROOT / "examples/skill-agent-pilot/skill"
PROMPT = ("Read the laomedo-pilot skill and fixture with shell tools. Then run "
          "exactly this shell command: sh -c 'sleep 30; printf CANCEL-TOO-LATE > "
          "cancel-marker.txt'. Do not run another command after it. The marker "
          "is only a cancellation sentinel.")


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def read_events(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def docker_state(name):
    if not name:
        return {"container_name": None, "inspect": "not_created", "ps_all": []}
    inspected = subprocess.run(["docker", "inspect", name], capture_output=True,
                               text=True, timeout=12)
    listing = subprocess.run(["docker", "ps", "-a", "--filter", "name=^" + name + "$",
                              "--format", "{{.Names}}"], capture_output=True,
                             text=True, timeout=12)
    return {"container_name": name,
            "inspect": "present" if inspected.returncode == 0 else "absent",
            "ps_all": listing.stdout.splitlines(),
            "query_errors": [inspected.stderr.strip() if inspected.returncode not in (0, 1) else "",
                             listing.stderr.strip() if listing.returncode else ""]}


class CaptureTransport:
    def __init__(self):
        self.servers = []

    def __call__(self, command, evidence):
        server = AppServer(command, evidence)
        self.servers.append(server)
        return server


def wait_terminal(runner, run_id, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        record = runner.status(run_id)
        if record["status"] not in {"prepared", "running"}:
            return record
        time.sleep(.1)
    return runner.status(run_id)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--allow-one-model-turn", action="store_true")
    args = parser.parse_args()
    if not args.allow_one_model_turn:
        parser.error("active case needs explicit --allow-one-model-turn")
    state = args.state.resolve()
    if state.exists() and any(state.iterdir()):
        parser.error("Phase B requires a fresh empty private state")
    state.mkdir(parents=True, exist_ok=True)
    store = state / "skill-store"
    reference = SkillStore(store).import_skill("laomedo-pilot", SKILL)
    transport = CaptureTransport()
    runner = LocalRunner(state / "runner", store, SOURCE, transport=transport,
                         max_model_turns=4)
    preflight = runner.preflight()
    assert preflight["status"] == "ready" and preflight["submitted_turns"] == 0
    assert any(x["id"] == "gpt-6-luna" and "low" in x["efforts"]
               for x in preflight["models"])
    ledger = state / "runner/turn-ledger.json"
    assert not ledger.exists()
    pins = {"protocol": digest(ROOT / "experiments/exp22/PHASE-B-AMENDMENT.md"),
            "implementation": subprocess.check_output(["git", "rev-parse", "HEAD"],
                                                       cwd=ROOT, text=True).strip(),
            "source_fixture": digest(SOURCE / "fixture.txt"),
            "skill": digest(SKILL / "SKILL.md"), "skill_revision": reference["revision_id"],
            "model": "gpt-6-luna", "effort": "low", "prompt_sha256": "sha256:" +
            hashlib.sha256(PROMPT.encode()).hexdigest(), "turn_cap": 4,
            "turns_before": 0, "image_id": preflight["image_id"]}
    (state / "pins.json").write_text(json.dumps(pins, indent=2), encoding="utf-8")
    base = {"model": "gpt-6-luna", "effort": "low", "skill_ref": {
        "skill_id": "laomedo-pilot", "revision_id": reference["revision_id"],
        "tree_hash": reference["revision_id"]}}

    gate = threading.Event()
    pre = runner.start_async({**base, "request_id": str(uuid4()),
                              "task": "This request must be cancelled before dispatch."},
                             response_gate=gate)
    pre_id = pre["run_id"]
    assert pre["status"] == "prepared" and not ledger.exists()
    pre_cancel = runner.cancel(pre_id)
    gate.set()
    pre_final = wait_terminal(runner, pre_id, 5)
    assert pre_cancel["status"] == "cancelled" and pre_final["status"] == "cancelled"
    assert not ledger.exists() and len(transport.servers) == 1  # preflight only
    pre_events_path = state / "runner/runs" / pre_id / "raw-events.jsonl"
    assert not read_events(pre_events_path)
    pre_result = {"run_id": pre_id, "status": pre_final["status"],
                  "cancel_confirmed": pre_final["cancel_confirmed"],
                  "thread_id": pre_final["thread_id"], "turns": pre_final["turns"],
                  "ledger_after": 0, "container": "not_created"}
    (state / "prethread.json").write_text(json.dumps(pre_result, indent=2), encoding="utf-8")

    active = runner.start_async({**base, "request_id": str(uuid4()), "task": PROMPT})
    run_id = active["run_id"]
    events_path = state / "runner/runs" / run_id / "raw-events.jsonl"
    start = time.monotonic()
    seen = None
    while time.monotonic() - start < 45:
        for event in read_events(events_path):
            item = (event.get("params") or {}).get("item") or {}
            if (event.get("method") == "item/started" and
                    item.get("type") == "commandExecution" and
                    "sleep 30" in str(item.get("command", ""))):
                seen = {"item_id": item.get("id"), "command_sha256": "sha256:" +
                        hashlib.sha256(str(item.get("command")).encode()).hexdigest(),
                        "seconds_after_ack": round(time.monotonic() - start, 3)}
                break
        if seen:
            break
        if runner.status(run_id)["status"] not in {"prepared", "running"}:
            break
        time.sleep(.1)
    accepted = runner.cancel(run_id)
    final = wait_terminal(runner, run_id, 30)
    all_events = read_events(events_path)
    server = transport.servers[-1] if len(transport.servers) > 1 else None
    container = docker_state(server.container_name if server else None)
    marker = state / "runner/runs" / run_id / "workspace/cancel-marker.txt"
    ledger_data = json.loads(ledger.read_text(encoding="utf-8")) if ledger.exists() else None
    native_completions = [e.get("params", {}).get("turn", {}).get("status")
                          for e in all_events if e.get("method") == "turn/completed"]
    result = {"run_id": run_id, "raw_event_ref": final.get("raw_event_ref"),
              "ack_status": active["status"], "tool_start": seen,
              "cancel_status": accepted["status"],
              "cancel_confirmed_on_accept": accepted["cancel_confirmed"],
              "final_status": final["status"],
              "final_error_category": final.get("error_category"),
              "cancel_confirmed": final.get("cancel_confirmed"),
              "native_thread_id_present": bool(final.get("thread_id")),
              "native_turns": final.get("turns"),
              "native_turn_completed_statuses": native_completions,
              "interrupt_acknowledged": server.interrupt_acknowledged if server else None,
              "raw_event_count": len(all_events), "raw_event_sha256": digest(events_path),
              "container": container, "sentinel_present": marker.exists(),
              "turn_ledger": ledger_data, "cross_store_trace_join": "not_verified"}
    (state / "active.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"state": str(state), "prethread": pre_result,
                      "active": result}, indent=2))


if __name__ == "__main__":
    main()
