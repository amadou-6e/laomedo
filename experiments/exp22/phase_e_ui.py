"""Disposable visible Langflow Playground Stop probe with one bounded turn."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from urllib.request import urlopen
from uuid import uuid4

from experiments.exp22.phase_c_live import _auth_read_result, _events, _is_long_command, _stop
from experiments.exp22.phase_d_live import (
    LANGFLOW_IMAGE, PILOT, ROOT, _audit_requests,
    _auth_mount_exists, _cleanup_runner_runs, _hash, _owned_container_absent,
    _port, _private_empty, _route_summary,
)
from laomedo.local_runner import LocalRunner, serve
from laomedo.skill_store import SkillStore


LEDGER = Path.home() / "AppData/Local/Laomedo/exp22-phase-c-turns.json"
PROTOCOL = ROOT / "experiments/exp22/PHASE-E-UI-PROTOCOL.md"
E_TASK = ROOT / "experiments/exp22/PHASE-E-TASK.txt"
BROWSER = ROOT / "experiments/exp22/phase_e_browser.cjs"
CAP = 12


def _reserve(state, attempt_id=None, result=None):
    """Use the shared lock and cap, preserving all historical entries."""
    lock = LEDGER.with_suffix(".lock")
    descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    try:
        ledger = json.loads(LEDGER.read_text(encoding="utf-8-sig"))
        if ledger.get("cap") != CAP or len(ledger.get("attempts", [])) < 4:
            raise RuntimeError("extended_ledger_unavailable")
        if attempt_id is None:
            if len(ledger["attempts"]) >= CAP:
                raise RuntimeError("extended_ledger_exhausted")
            attempt_id = uuid4().hex
            ledger["attempts"].append({"id": attempt_id, "state_dir": str(state),
                                       "submitted_at": time.time(),
                                       "result": "submitted_unknown"})
        else:
            matches = [item for item in ledger["attempts"] if item.get("id") == attempt_id]
            if len(matches) != 1:
                raise RuntimeError("attempt_missing")
            matches[0]["result"] = result
            matches[0]["finished_at"] = time.time()
        pending = LEDGER.with_suffix(".pending")
        pending.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        os.replace(pending, LEDGER)
        return attempt_id, len(ledger["attempts"])
    finally:
        lock.unlink(missing_ok=True)


def _wait_ui(port, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}/api/v1/auto_login", timeout=3) as response:
                if response.status == 200:
                    if "access_token" in json.loads(response.read()):
                        return
        except Exception:
            pass
        time.sleep(.5)
    raise RuntimeError("disposable_langflow_not_ready")


def _remove_ui(name):
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=20)
    inspected = subprocess.run(["docker", "inspect", name], capture_output=True, timeout=12)
    return inspected.returncode != 0 and b"No such" in inspected.stderr


def _ui_attribution(observed, cancels, terminal_observed_epoch):
    if len(cancels) != 1 or not observed.get("runner_terminal_signal_seen"):
        return False
    click = observed.get("stop_click_begin_epoch")
    close = observed.get("context_close_begin_epoch")
    route = cancels[0].get("at_epoch_seconds")
    return bool(click and route and terminal_observed_epoch and close and
                click <= route < terminal_observed_epoch < close)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--allow-one-model-turn", action="store_true")
    args = parser.parse_args()
    if args.preflight_only == args.allow_one_model_turn:
        parser.error("select_exactly_one_mode")
    if args.allow_one_model_turn and subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=ROOT, text=True).strip():
        parser.error("reviewed_source_must_be_committed_and_clean")
    state = _private_empty(args.state)
    (state / "langflow-data").mkdir()
    if not _auth_mount_exists():
        raise RuntimeError("private_login_copy_absent")
    skill = SkillStore(state / "skills").import_skill("laomedo-pilot", PILOT / "skill")
    runner = LocalRunner(state / "runner", state / "skills", PILOT / "source",
                         max_model_turns=1, supervise_containers=False)
    preflight = runner.preflight()
    if (preflight.get("status") != "ready" or preflight.get("image_id") is None or
            not any(item.get("id") == "gpt-6-luna" and "low" in item.get("efforts", [])
                    for item in preflight.get("models", []))):
        raise RuntimeError("runner_preflight_failed")
    runner_port, ui_port = _port(), _port()
    server = serve(runner, port=runner_port)
    routes = state / "runner-routes.jsonl"
    _audit_requests(server, routes)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    name = "laomedo-phase-e-ui-" + uuid4().hex[:16]
    token = state / "runner/api-token"
    command = ["docker", "run", "-d", "--rm", "--pull=never", "--name", name,
               "-p", f"127.0.0.1:{ui_port}:7860", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges",
               "--mount", f"type=bind,source={ROOT / 'components'},target=/app/custom_components,readonly",
               "--mount", f"type=bind,source={token},target=/run/secrets/laomedo-runner-token,readonly",
               "--mount", f"type=bind,source={state / 'langflow-data'},target=/app/langflow",
               "-e", "LANGFLOW_COMPONENTS_PATH=/app/custom_components",
               "-e", "LANGFLOW_AUTO_LOGIN=true", "-e", "DO_NOT_TRACK=true",
               "-e", "LAOMEDO_RUNNER_TOKEN_FILE=/run/secrets/laomedo-runner-token",
               LANGFLOW_IMAGE]
    attempt_id = None
    run_id = None
    category = "not_submitted"
    browser = None
    output = None
    teardown = {"category": category, "ui_container_absent": None,
                "exact_runner_cleanup_verified": None}
    try:
        started = subprocess.run(command, capture_output=True, timeout=30)
        if started.returncode != 0:
            raise RuntimeError("disposable_langflow_start_failed")
        _wait_ui(ui_port)
        pins = {"implementation": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "protocol": _hash(PROTOCOL), "task": _hash(E_TASK),
                "browser": _hash(BROWSER),
                "flow": _hash(ROOT / "examples/native-codex-node/flow.json"),
                "component": _hash(ROOT / "components/laomedo/codex_agent.py"),
                "skill_revision": skill["revision_id"],
                "skill": _hash(PILOT / "skill/SKILL.md"),
                "source": _hash(PILOT / "source/fixture.txt"),
                "codex_image_id": preflight["image_id"],
                "langflow_image": LANGFLOW_IMAGE, "model": "gpt-6-luna",
                "effort": "low", "shared_turn_cap": CAP}
        (state / "pins.json").write_text(json.dumps(pins, indent=2), encoding="utf-8")
        base = ["node", str(BROWSER), "prepare", str(state), str(ui_port),
                str(runner_port), skill["revision_id"]]
        prepared = subprocess.run(base, capture_output=True, text=True, timeout=90)
        if prepared.returncode != 0:
            raise RuntimeError("playground_prepare_failed")
        preparation = json.loads((state / "browser-prepare.json").read_text(encoding="utf-8"))
        if not preparation.get("playground_available") or preparation.get("error_class"):
            raise RuntimeError("playground_unavailable")
        if args.preflight_only:
            category = "no_model_preflight_passed"
            summary = {"category": category, "model_turn_submitted": False,
                       "playground_available": True, "flow_id": preparation["flow_id"],
                       "runner_ready": True, "langflow_ready": True}
            (state / "sanitized.json").write_text(json.dumps(summary, indent=2),
                                                     encoding="utf-8")
            print(json.dumps(summary))
            return
        attempt_id, used = _reserve(state)
        category = "submitted_unknown"
        output = (state / "browser.log").open("w", encoding="utf-8")
        browser = subprocess.Popen(["node", str(BROWSER), "run", str(state),
                                    str(ui_port), str(runner_port), skill["revision_id"]],
                                   stdout=output, stderr=subprocess.STDOUT, cwd=ROOT)
        deadline = time.monotonic() + 55
        long_started = False
        while time.monotonic() < deadline:
            records = list((state / "runner/runs").glob("*/record.json"))
            if len(records) > 1:
                raise RuntimeError("duplicate_runner_dispatch")
            if records:
                run_id = records[0].parent.name
                events = _events(records[0].parent / "raw-events.jsonl")
                auth_result, _ = _auth_read_result(events)
                if auth_result == "readable":
                    raise RuntimeError("agent_login_readable")
                if any(_is_long_command(event) for event in events):
                    long_started = True
                    break
            if browser.poll() is not None:
                break
            time.sleep(.1)
        (state / "stop-now.signal").write_text("stop", encoding="ascii")
        terminal_observed_epoch = None
        final = None
        if run_id:
            terminal_deadline = time.monotonic() + 35
            while time.monotonic() < terminal_deadline:
                final = runner.status(run_id)
                if final["status"] not in {"prepared", "running"}:
                    terminal_observed_epoch = time.time()
                    (state / "runner-terminal.signal").write_text("terminal", encoding="ascii")
                    break
                time.sleep(.1)
        browser.wait(timeout=50)
        observed = json.loads((state / "browser-run.json").read_text(encoding="utf-8"))
        if not run_id:
            raise RuntimeError("runner_run_id_missing")
        final = runner.status(run_id)
        raw = state / "runner/runs" / run_id / "raw-events.jsonl"
        events = _events(raw)
        auth_result, auth_index = _auth_read_result(events)
        native = [event.get("params", {}).get("turn", {}).get("status")
                  for event in events if event.get("method") == "turn/completed"]
        time.sleep(31)
        marker = state / "runner/runs" / run_id / "workspace/cancel-marker.txt"
        traffic = _route_summary(routes, run_id, final.get("client_request_id"))
        cancels = [row for row in _events(routes) if row.get("kind") == "cancel"]
        attributed = _ui_attribution(observed, cancels, terminal_observed_epoch)
        summary = {"category": None, "shared_turn_count": used,
                   "flow_id": observed.get("flow_id"),
                   "browser_send_clicked": observed.get("send_clicked"),
                   "browser_stop_clicked": observed.get("stop_clicked"),
                   "browser_stop_signal_seen": observed.get("stop_signal_seen"),
                   "browser_terminal_signal_seen": observed.get("runner_terminal_signal_seen"),
                   "ui_cancel_attributed_before_disconnect": attributed,
                   "browser_stop_control_visible": observed.get("stop_control_visible"),
                   "browser_requests": observed.get("browser_requests"),
                   "long_command_started": long_started,
                   "run_id": run_id, "request_id": final.get("client_request_id"),
                   "runner_routes": traffic, "runner_status": final.get("status"),
                   "cancel_confirmed": final.get("cancel_confirmed"),
                   "auth_read": auth_result, "auth_event_index": auth_index,
                   "native_completion_statuses": native,
                   "raw_event_count": len(events), "raw_event_sha256": _hash(raw),
                   "exact_container_absent": _owned_container_absent(final),
                   "late_sentinel_absent": not marker.exists()}
        category = ("visible_stop_native_cancel_passed" if browser.returncode == 0
                    and observed.get("send_clicked") and observed.get("stop_clicked")
                    and observed.get("stop_signal_seen") and attributed
                    and long_started and traffic["exact_identity_match"]
                    and auth_result == "denied" and final.get("status") == "cancelled"
                    and final.get("cancel_confirmed") is True
                    and "interrupted" in native and summary["exact_container_absent"]
                    and summary["late_sentinel_absent"] else
                    "visible_stop_native_cancel_inconclusive")
        summary["category"] = category
        (state / "sanitized.json").write_text(json.dumps(summary, indent=2),
                                                 encoding="utf-8")
        print(json.dumps(summary))
    finally:
        teardown["category"] = category
        if browser and browser.poll() is None:
            try:
                _stop(browser, tree=True)
                teardown["browser_stopped"] = browser.poll() is not None
            except Exception as exc:
                teardown["browser_stop_error"] = type(exc).__name__
        if attempt_id:
            try:
                _reserve(state, attempt_id=attempt_id, result=category)
            except Exception as exc:
                teardown["ledger_update_error"] = type(exc).__name__
        try:
            cleaned = _cleanup_runner_runs(runner, state / "runner/runs", run_id)
            teardown["runs"] = cleaned
            teardown["exact_runner_cleanup_verified"] = all(
                item["exact_cleanup_verified"] for item in cleaned) if cleaned else True
        except Exception as exc:
            teardown["runner_cleanup_error"] = type(exc).__name__
        try:
            teardown["ui_container_absent"] = _remove_ui(name)
        except Exception as exc:
            teardown["ui_cleanup_error"] = type(exc).__name__
        (state / "teardown.json").write_text(json.dumps(teardown, indent=2),
                                              encoding="utf-8")
        server.shutdown()
        server.server_close()
        if output:
            output.close()


if __name__ == "__main__":
    main()
