"""Visible Playground Stop while a real runner run is still prepared."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from uuid import uuid4

from experiments.exp22.phase_c_live import _events, _stop
from experiments.exp22.phase_d_live import (
    LANGFLOW_IMAGE, PILOT, ROOT, _audit_requests, _auth_mount_exists,
    _cleanup_runner_runs, _hash, _port, _private_empty, _route_summary,
)
from experiments.exp22.phase_e_ui import (
    BROWSER, CAP, _flow_code_pins, _remove_ui, _reserve, _ui_attribution,
    _wait_ui,
)
from laomedo.local_runner import LocalRunner, serve
from laomedo.skill_store import SkillStore


PROTOCOL = ROOT / "experiments/exp22/PHASE-F-PRETHREAD-PROTOCOL.md"
TASK = ROOT / "experiments/exp22/PHASE-F-TASK.txt"


def _hold_async_ack(server, runner, release):
    original = server.RequestHandlerClass
    waiting = threading.Event()

    class HeldHandler(original):
        def _reply(self, code, value):
            if (self.command == "POST" and self.path.split("?", 1)[0] ==
                    "/v1/runs/async" and code == 202 and
                    value.get("status") == "prepared"):
                waiting.set()
                if not release.wait(timeout=90):
                    # Never release a prepared worker after a failed hold.
                    runner.cancel(value["run_id"])
                    release.set()
            return super()._reply(code, value)

    server.RequestHandlerClass = HeldHandler
    return waiting


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--allow-one-submission", action="store_true")
    args = parser.parse_args()
    if args.preflight_only == args.allow_one_submission:
        parser.error("select_exactly_one_mode")
    if args.allow_one_submission and subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=ROOT, text=True).strip():
        parser.error("reviewed_source_must_be_committed_and_clean")
    code_pins = _flow_code_pins()
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
    release_ack = threading.Event()
    ack_waiting = _hold_async_ack(server, runner, release_ack)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    name = "laomedo-phase-f-ui-" + uuid4().hex[:16]
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
    browser = None
    output = None
    category = "not_submitted"
    teardown = {"category": category, "ui_container_absent": None,
                "exact_runner_cleanup_verified": None}
    try:
        started = subprocess.run(command, capture_output=True, timeout=30)
        if started.returncode != 0:
            raise RuntimeError("disposable_langflow_start_failed")
        _wait_ui(ui_port)
        pins = {"implementation": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "protocol": _hash(PROTOCOL), "task": _hash(TASK),
                "browser": _hash(BROWSER),
                "flow": _hash(ROOT / "examples/native-codex-node/flow.json"),
                "embedded_component_code": code_pins,
                "skill_revision": skill["revision_id"],
                "codex_image_id": preflight["image_id"],
                "langflow_image": LANGFLOW_IMAGE, "shared_turn_cap": CAP}
        (state / "pins.json").write_text(json.dumps(pins, indent=2), encoding="utf-8")
        env = {key: value for key, value in os.environ.items()
               if key != "PHASE_E_FAKE_PREFLIGHT"}
        env["PHASE_E_PRETHREAD"] = "1"
        base = ["node", str(BROWSER), "prepare", str(state), str(ui_port),
                str(runner_port), skill["revision_id"]]
        prepared = subprocess.run(base, cwd=ROOT, env=env, capture_output=True,
                                  timeout=90)
        if prepared.returncode != 0:
            raise RuntimeError("prethread_playground_prepare_failed")
        prep = json.loads((state / "browser-prepare.json").read_text(encoding="utf-8"))
        if not prep.get("playground_available") or prep.get("error_class"):
            raise RuntimeError("prethread_playground_unavailable")
        if args.preflight_only:
            category = "no_model_preflight_passed"
            result = {"category": category, "model_turn_submitted": False,
                      "playground_available": True, "flow_id": prep["flow_id"],
                      "runner_ready": True, "langflow_ready": True}
            (state / "sanitized.json").write_text(json.dumps(result, indent=2),
                                                     encoding="utf-8")
            print(json.dumps(result))
            return
        attempt_id, used = _reserve(state)
        category = "submitted_unknown"
        output = (state / "browser.log").open("w", encoding="utf-8")
        browser = subprocess.Popen(["node", str(BROWSER), "run", str(state),
                                    str(ui_port), str(runner_port), skill["revision_id"]],
                                   cwd=ROOT, env=env, stdout=output,
                                   stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            records = list((state / "runner/runs").glob("*/record.json"))
            if len(records) > 1:
                raise RuntimeError("duplicate_runner_dispatch")
            if records and ack_waiting.is_set():
                run_id = records[0].parent.name
                if runner.status(run_id)["status"] != "prepared":
                    raise RuntimeError("worker_started_before_stop")
                break
            if browser.poll() is not None:
                break
            time.sleep(.1)
        if not run_id:
            raise RuntimeError("prepared_run_not_observed")
        (state / "stop-now.signal").write_text("stop", encoding="ascii")
        terminal_epoch = None
        host_fallback_cancel_used = False
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            current = runner.status(run_id)
            if current["status"] == "cancelled" and current.get("cancel_confirmed"):
                terminal_epoch = time.time()
                (state / "runner-terminal.signal").write_text("terminal", encoding="ascii")
                break
            if current["status"] not in {"prepared", "running"}:
                break
            time.sleep(.1)
        if terminal_epoch is None:
            current = runner.status(run_id)
            if current["status"] in {"prepared", "running"}:
                runner.cancel(run_id)
                host_fallback_cancel_used = True
        release_ack.set()
        browser.wait(timeout=50)
        observed = json.loads((state / "browser-run.json").read_text(encoding="utf-8"))
        time.sleep(.3)
        final = runner.status(run_id)
        raw = state / "runner/runs" / run_id / "raw-events.jsonl"
        traffic = _route_summary(routes, run_id, final.get("client_request_id"))
        cancels = [row for row in _events(routes) if row.get("kind") == "cancel"]
        attributed = _ui_attribution(observed, cancels, terminal_epoch)
        native_events = _events(raw)
        turn_file = state / "runner/turn-ledger.json"
        result = {"category": None, "shared_turn_count": used,
                  "run_id": run_id, "request_id": final.get("client_request_id"),
                  "browser_send_clicked": observed.get("send_clicked"),
                  "browser_stop_clicked": observed.get("stop_clicked"),
                  "browser_stop_signal_seen": observed.get("stop_signal_seen"),
                  "ui_cancel_attributed_before_disconnect": attributed,
                  "ack_was_held": ack_waiting.is_set(),
                  "host_fallback_cancel_used": host_fallback_cancel_used,
                  "runner_routes": traffic, "runner_status": final.get("status"),
                  "cancel_confirmed": final.get("cancel_confirmed"),
                  "thread_id_absent": final.get("thread_id") is None,
                  "container_not_launched": not final.get("container_ownership"),
                  "native_event_count": len(native_events),
                  "runner_turn_ledger_absent": not turn_file.exists(),
                  "runner_run_count": len(list((state / "runner/runs").glob("*/record.json")))}
        category = ("visible_prethread_cancel_passed" if browser.returncode == 0 and
                    observed.get("send_clicked") and observed.get("stop_clicked") and
                    observed.get("stop_signal_seen") and attributed and
                    not host_fallback_cancel_used and
                    traffic["exact_identity_match"] and
                    final.get("status") == "cancelled" and
                    final.get("cancel_confirmed") is True and
                    result["thread_id_absent"] and result["container_not_launched"] and
                    result["native_event_count"] == 0 and result["runner_turn_ledger_absent"]
                    and result["runner_run_count"] == 1 else
                    "visible_prethread_cancel_inconclusive")
        result["category"] = category
        (state / "sanitized.json").write_text(json.dumps(result, indent=2),
                                                 encoding="utf-8")
        print(json.dumps(result))
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
            if run_id and runner.status(run_id)["status"] == "prepared":
                runner.cancel(run_id)
            release_ack.set()
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
