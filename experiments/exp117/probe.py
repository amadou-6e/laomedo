"""One bounded real Codex Playground turn through the opt-in host join."""

import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
from uuid import UUID, uuid4

from experiments.exp117.support import (
    _auth_read_result, _events, _is_long_command, _stop, LANGFLOW_IMAGE, PILOT,
    ROOT, _audit_requests, _auth_mount_exists, _cleanup_runner_runs, _hash,
    _owned_container_absent, _port, _private_empty, BROWSER, CAP, _flow_code_pins,
    _remove_ui, _reserve, _ui_attribution, _wait_ui,
)
from laomedo.langflow_join_service import build_service
from laomedo.local_runner import LocalRunner, serve
from laomedo.skill_store import SkillStore
from laomedo.work_graph.local_launch import LangflowLocalClient
from laomedo.workflow_run_store import WorkflowRunStore


PROTOCOL = ROOT / "experiments/exp117/PROTOCOL.md"
TASK = ROOT / "experiments/exp117/PHASE-E-TASK.txt"


def _audit_bridge_requests(server, path):
    """Record only authenticated bridge route identities and receipt time."""
    original = server.RequestHandlerClass
    lock = threading.Lock()

    class AuditedHandler(original):
        def authorized(self):
            accepted = super().authorized()
            route = self.path.split("?", 1)[0]
            kind = ("start" if self.command == "POST" and route == "/v1/invocations"
                    else "cancel" if self.command == "POST" and route.startswith(
                        "/v1/requests/") and route.endswith("/cancel") else None)
            if accepted and kind:
                with lock, path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"kind": kind, "path": route,
                                             "at_epoch_seconds": time.time()}) + "\n")
            return accepted

    server.RequestHandlerClass = AuditedHandler


def _restart_join(state, flow_id, ui_port, command, name, bridge, bridge_thread,
                  runner_rows, host_rows, original_trace):
    """Reopen both stores after closing the bridge; never redispatch a request."""
    bridge.shutdown()
    bridge.server_close()
    bridge_thread.join(timeout=3)
    if bridge_thread.is_alive() or not _remove_ui(name):
        raise RuntimeError("first_services_not_stopped")
    if subprocess.run(command, capture_output=True, timeout=30).returncode:
        raise RuntimeError("disposable_langflow_restart_failed")
    _wait_ui(ui_port)
    fetched = LangflowLocalClient(f"http://127.0.0.1:{ui_port}").fetch(flow_id)
    db_path = state / "langflow-data/langflow.db"
    if not db_path.is_file():
        raise RuntimeError("private_langflow_database_missing")
    snapshot_path = state / "langflow-restart-snapshot.db"
    with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(snapshot_path) as snapshot:
            source.backup(snapshot)
    reopened = subprocess.run(
        [sys.executable, "-m", "experiments.exp117.reopen",
         "--state", str(state), "--reopen-host"],
        cwd=ROOT, capture_output=True, text=True, timeout=20, check=True)
    child_rows = json.loads(reopened.stdout)
    if len(host_rows) != 1 or len(child_rows) != 1 or not host_rows[0]["graph_run_id"]:
        raise RuntimeError("private_host_binding_missing")
    graph_id = host_rows[0]["graph_run_id"]
    with sqlite3.connect(snapshot_path.as_uri() + "?mode=ro", uri=True) as db:
        trace_ids = [row[0] for row in db.execute("""SELECT DISTINCT s.trace_id
            FROM span s JOIN trace t ON t.id=s.trace_id WHERE t.flow_id=? AND
            (instr(CAST(s.inputs AS TEXT),?)>0 OR
             instr(CAST(s.outputs AS TEXT),?)>0)""",
            (UUID(flow_id).hex, graph_id, graph_id))]
    native = runner_rows[0] if len(runner_rows) == 1 else None
    child = child_rows[0]
    identity = bool(native and original_trace and all(
        child[key] == host_rows[0][key] for key in
        ("client_request_id", "run_id", "invocation_id", "flow_id", "graph_run_id"))
        and child["trace_id"] == original_trace["trace_id"]
        and child["runner_request_hash"] ==
        original_trace["invocation"]["runner_request_hash"]
        and child["runner_request_hash"] == native["request_hash"]
        and child["runner_request_id"] == host_rows[0]["invocation_id"]
        and child["runner_run_id"] == native["run_id"]
        and child["runner_raw_event_ref"] == native["raw_event_ref"]
        and child["runner_provider"] == "codex"
        and child["status"] == original_trace["run_status"]
        and child["dispatch_attempts"] == 1)
    return {"saved_flow_reopened": fetched.get("id") == flow_id,
            "host_binding_reopened_in_child": identity,
            "langflow_trace_count": len(trace_ids),
            "langflow_trace_id_present": bool(trace_ids and trace_ids[0]),
            "trace_join_basis": "saved_flow_uuid_and_reported_graph_id_in_span",
            "executing_graph_attested": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--prethread", action="store_true")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight-only", action="store_true")
    modes.add_argument("--allow-one-model-turn", action="store_true")
    args = parser.parse_args()
    if args.allow_one_model_turn and subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=ROOT, text=True).strip():
        parser.error("reviewed_source_must_be_committed_and_clean")
    component_pins = _flow_code_pins()
    state = _private_empty(args.state)
    (state / "langflow-data").mkdir()
    if not _auth_mount_exists():
        raise RuntimeError("private_login_copy_absent")
    skill = SkillStore(state / "skills").import_skill("laomedo-pilot", PILOT / "skill")
    runner = LocalRunner(state / "runner", state / "skills", PILOT / "source",
                         max_model_turns=1)
    preflight = runner.preflight()
    if (preflight.get("status") != "ready" or not preflight.get("image_id") or
            not any(item.get("id") == "gpt-6-luna" and "low" in item.get("efforts", [])
                    for item in preflight.get("models", []))):
        raise RuntimeError("runner_preflight_failed")
    runner_port, bridge_port, ui_port = _port(), _port(), _port()
    runner_server = serve(runner, port=runner_port)
    routes = state / "runner-routes.jsonl"
    bridge_routes = state / "bridge-routes.jsonl"
    _audit_requests(runner_server, routes)
    release_ack = threading.Event()
    ack_waiting = None
    if args.prethread:
        original_handler = runner_server.RequestHandlerClass
        ack_waiting = threading.Event()
        class HeldHandler(original_handler):
            def _reply(self, code, value):
                if self.command == "POST" and self.path == "/v1/runs/async" and code == 202:
                    ack_waiting.set()
                    release_ack.wait()
                return super()._reply(code, value)
        runner_server.RequestHandlerClass = HeldHandler
    runner_thread = threading.Thread(target=runner_server.serve_forever, daemon=True)
    runner_thread.start()
    bridge_token_path = state / "bridge-token"
    bridge_token_path.write_text(uuid4().hex, encoding="ascii")
    bridge = None
    browser = None
    browser_log = None
    attempt_id = None
    run_id = None
    category = "not_submitted"
    name = "laomedo-g-live-" + uuid4().hex[:12]
    teardown = {"category": category, "langflow_absent": None,
                "bridge_stopped": None, "exact_runner_cleanup_verified": None}
    try:
        command = ["docker", "run", "-d", "--rm", "--pull=never", "--name", name,
                   "-p", f"127.0.0.1:{ui_port}:7860", "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges",
                   "--mount", f"type=bind,source={ROOT / 'components'},target=/app/custom_components,readonly",
                   "--mount", f"type=bind,source={bridge_token_path},target=/run/secrets/laomedo-bridge-token,readonly",
                   "--mount", f"type=bind,source={state / 'langflow-data'},target=/app/data",
                   "-e", "LANGFLOW_COMPONENTS_PATH=/app/custom_components",
                   "-e", "LANGFLOW_AUTO_LOGIN=true", "-e", "DO_NOT_TRACK=true",
                   "-e", "LANGFLOW_DATABASE_URL=sqlite:////app/data/langflow.db",
                   LANGFLOW_IMAGE]
        if subprocess.run(command, capture_output=True, timeout=30).returncode:
            raise RuntimeError("disposable_langflow_start_failed")
        _wait_ui(ui_port)
        bridge = build_service(
            store_path=state / "join.sqlite3", bridge_token_file=bridge_token_path,
            runner_token_file=state / "runner/api-token",
            langflow_url=f"http://127.0.0.1:{ui_port}",
            runner_url=f"http://127.0.0.1:{runner_port}", port=bridge_port)
        _audit_bridge_requests(bridge, bridge_routes)
        bridge_thread = threading.Thread(target=bridge.serve_forever, daemon=True)
        bridge_thread.start()
        pins = {"implementation": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "protocol": _hash(PROTOCOL), "task": _hash(TASK),
                "browser": _hash(BROWSER),
                "flow": _hash(ROOT / "examples/native-codex-node/flow.json"),
                "component_code": component_pins,
                "skill_revision": skill["revision_id"],
                "codex_image_id": preflight["image_id"],
                "langflow_image": LANGFLOW_IMAGE,
                "model": "gpt-6-luna", "effort": "low", "shared_turn_cap": CAP}
        (state / "pins.json").write_text(json.dumps(pins, indent=2), encoding="utf-8")
        base = ["node", str(BROWSER), "prepare", str(state), str(ui_port),
                str(bridge_port), skill["revision_id"]]
        env = {**os.environ, "PHASE_G_JOIN": "1"}
        env.pop("PHASE_E_FAKE_PREFLIGHT", None)
        env.pop("PHASE_E_PRETHREAD", None)
        if args.prethread:
            env["PHASE_E_PRETHREAD"] = "1"
        prepared = subprocess.run(base, cwd=ROOT, env=env,
                                  capture_output=True, text=True, timeout=90)
        if prepared.returncode:
            raise RuntimeError("playground_prepare_failed")
        preparation = json.loads((state / "browser-prepare.json").read_text())
        if not preparation.get("playground_available") or preparation.get("error_class"):
            raise RuntimeError("playground_unavailable")
        if args.preflight_only:
            category = "no_model_preflight_passed"
            summary = {"category": category, "model_turn_submitted": False,
                       "runner_ready": True, "flow_id": preparation["flow_id"],
                       "bridge_ready": True, "langflow_ready": True}
            (state / "sanitized.json").write_text(json.dumps(summary, indent=2))
            print(json.dumps(summary))
            return
        attempt_id, used = _reserve(state)
        category = "submitted_unknown"
        browser_log = (state / "browser.log").open("w", encoding="utf-8")
        base[2] = "run"
        browser = subprocess.Popen(base, cwd=ROOT, env=env, stdout=browser_log,
                                   stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 55
        long_started = False
        long_seen_at = None
        while time.monotonic() < deadline:
            records = list((state / "runner/runs").glob("*/record.json"))
            if len(records) > 1:
                raise RuntimeError("duplicate_runner_dispatch")
            if records:
                run_id = records[0].parent.name
                raw = records[0].parent / "raw-events.jsonl"
                events = _events(raw) if raw.exists() else []
                auth_read, _ = _auth_read_result(events)
                if auth_read == "readable":
                    raise RuntimeError("agent_login_readable")
                if args.prethread and ack_waiting.is_set():
                    if runner.status(run_id)["status"] != "prepared":
                        raise RuntimeError("worker_started_before_stop")
                    break
                if any(_is_long_command(event) for event in events):
                    long_started, long_seen_at = True, time.time()
                    break
            if browser.poll() is not None:
                break
            time.sleep(.1)
        (state / "stop-now.signal").write_text("stop", encoding="ascii")
        terminal_seen_at = None
        if run_id:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                final = runner.status(run_id)
                if final["status"] not in {"prepared", "running"}:
                    terminal_seen_at = time.time()
                    (state / "runner-terminal.signal").write_text("terminal", encoding="ascii")
                    break
                time.sleep(.1)
        if args.prethread:
            confirmed = runner.status(run_id)
            if confirmed["status"] != "cancelled" or not confirmed.get("cancel_confirmed"):
                raise RuntimeError("prethread_release_refused")
            release_ack.set()
        browser.wait(timeout=55)
        observed = json.loads((state / "browser-run.json").read_text())
        if not run_id:
            raise RuntimeError("runner_run_id_missing")
        final = runner.status(run_id)
        if final["status"] in {"prepared", "running"}:
            raise RuntimeError("native_not_terminal_before_restart")
        raw = state / "runner/runs" / run_id / "raw-events.jsonl"
        events = _events(raw) if raw.exists() else []
        auth_read, auth_index = _auth_read_result(events)
        native = [event.get("params", {}).get("turn", {}).get("status")
                  for event in events if event.get("method") == "turn/completed"]
        if long_seen_at:
            time.sleep(max(0, 31 - (time.time() - long_seen_at)))
        marker = state / "runner/runs" / run_id / "workspace/cancel-marker.txt"
        route_rows = _events(routes)
        starts = [item for item in route_rows if item.get("kind") == "start"]
        cancels = [item for item in route_rows if item.get("kind") == "cancel"]
        bridge_rows = _events(bridge_routes)
        bridge_starts = [item for item in bridge_rows if item.get("kind") == "start"]
        bridge_cancels = [item for item in bridge_rows if item.get("kind") == "cancel"]
        attribution = _ui_attribution(observed, cancels, terminal_seen_at)
        store = WorkflowRunStore(state / "join.sqlite3")
        with store._database() as db:
            bindings = [dict(row) for row in db.execute(
                "SELECT * FROM langflow_client_requests")]
        host_trace = store.trace_snapshot(bindings[0]["run_id"]) if len(bindings) == 1 else None
        runner_rows = [final]
        starts_before_restart = len(starts)
        restart = _restart_join(state, observed["flow_id"], ui_port, command,
                                name, bridge, bridge_thread, runner_rows,
                                bindings, host_trace)
        bridge = None
        teardown["bridge_stopped"] = True
        starts_after_restart = sum(item.get("kind") == "start" for item in _events(routes))
        restart["native_starts_total"] = starts_after_restart
        restart["native_starts_after_restart"] = starts_after_restart - starts_before_restart
        identity = bool(host_trace and len(bindings) == 1 and
                        bindings[0]["invocation_id"] == final.get("client_request_id") and
                        host_trace["invocation"]["runner_run_id"] == run_id and
                        host_trace["invocation"]["runner_raw_event_ref"] ==
                        final.get("raw_event_ref"))
        bridge_attribution = bool(len(bridge_starts) == 1 and
            len(bridge_cancels) == 1 and len(cancels) == 1 and len(bindings) == 1 and
            bridge_starts[0]["path"] == "/v1/invocations" and
            bridge_cancels[0]["path"] ==
            "/v1/requests/" + bindings[0]["client_request_id"] + "/cancel" and
            observed.get("stop_click_begin_epoch") and
            observed.get("context_close_begin_epoch") and terminal_seen_at and
            observed["stop_click_begin_epoch"] <=
            bridge_cancels[0]["at_epoch_seconds"] <=
            cancels[0]["at_epoch_seconds"] < terminal_seen_at <
            observed["context_close_begin_epoch"])
        passed = (browser.returncode == 0 and observed.get("send_clicked") and
                  observed.get("stop_clicked") and attribution and
                  (long_started or args.prethread) and
                  bridge_attribution and
                  len(starts) == 1 and len(cancels) == 1 and identity and
                  (auth_read == "denied" or args.prethread) and final.get("status") == "cancelled" and
                  final.get("cancel_confirmed") is True and
                  ("interrupted" in native or args.prethread) and
                  (_owned_container_absent(final) or
                   (args.prethread and not final.get("container_ownership"))) and
                  not marker.exists() and restart["saved_flow_reopened"] and
                  restart["host_binding_reopened_in_child"] and
                  restart["langflow_trace_count"] == 1 and
                  restart["langflow_trace_id_present"] and
                  restart["native_starts_total"] == 1 and
                  restart["native_starts_after_restart"] == 0)
        if args.prethread:
            passed = (passed and not final.get("thread_id") and not events and
                not (state / "runner/turn-ledger.json").exists())
        category = ("prethread_join_visible_stop_passed" if args.prethread else
                    "real_join_visible_stop_passed") if passed else "real_join_inconclusive"
        summary = {"category": category, "shared_turn_count": used,
                   "browser_send_clicked": observed.get("send_clicked"),
                   "browser_stop_clicked": observed.get("stop_clicked"),
                   "ui_cancel_attributed_before_disconnect": attribution,
                   "bridge_cancel_attributed_before_runner": bridge_attribution,
                   "native_long_command_started": long_started,
                   "runner_status": final.get("status"),
                   "cancel_confirmed": final.get("cancel_confirmed"),
                   "auth_read": auth_read, "auth_event_index": auth_index,
                   "native_completion_statuses": native,
                   "raw_event_count": len(events),
                   "raw_event_sha256": _hash(raw) if raw.exists() else None,
                   "exact_container_absent": _owned_container_absent(final) if not args.prethread else
                       not final.get("container_ownership"),
                   "prethread": args.prethread,
                   "thread_id_absent": not final.get("thread_id"),
                   "runner_turn_ledger_absent": not (state / "runner/turn-ledger.json").exists(),
                   "late_sentinel_absent": not marker.exists(),
                   "host_runner_identity_match": identity,
                   "runner_route_starts": len(starts),
                   "runner_route_cancels": len(cancels), "restart": restart,
                   "bridge_route_starts": len(bridge_starts),
                   "bridge_route_cancels": len(bridge_cancels),
                   "executing_graph_attested": False}
        (state / "sanitized.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, sort_keys=True))
    finally:
        teardown["category"] = category
        if attempt_id:
            try:
                _reserve(state, attempt_id=attempt_id, result=category)
            except Exception as exc:
                teardown["ledger_update_error"] = type(exc).__name__
        if browser and browser.poll() is None:
            try:
                _stop(browser, tree=True)
            except Exception as exc:
                teardown["browser_stop_error"] = type(exc).__name__
        try:
            cleaned = _cleanup_runner_runs(runner, state / "runner/runs", run_id)
            if args.prethread and all(item["terminal_status"] == "cancelled" for item in cleaned):
                release_ack.set()
            teardown["runs"] = cleaned
            teardown["exact_runner_cleanup_verified"] = all(
                item["exact_cleanup_verified"] for item in cleaned) if cleaned else True
        except Exception as exc:
            teardown["runner_cleanup_error"] = type(exc).__name__
        if bridge:
            bridge.shutdown()
            bridge.server_close()
            bridge_thread.join(timeout=3)
            teardown["bridge_stopped"] = not bridge_thread.is_alive()
        runner_server.shutdown()
        runner_server.server_close()
        runner_thread.join(timeout=3)
        teardown["runner_server_stopped"] = not runner_thread.is_alive()
        teardown["langflow_absent"] = _remove_ui(name)
        if browser_log:
            browser_log.close()
        (state / "teardown.json").write_text(json.dumps(teardown, indent=2))


if __name__ == "__main__":
    main()
