"""Credential-free installed Playground check of the opt-in host join route.

The native runner is synthetic. No provider credential, model or real runner is
started. All raw browser and server state stays in a private directory.
"""

import argparse
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from experiments.exp22.phase_d_live import LANGFLOW_IMAGE, ROOT, _port, _private_empty
from experiments.exp22.phase_e_ui import BROWSER, _remove_ui, _wait_ui
from laomedo.langflow_join_service import build_service
from laomedo.work_graph.local_launch import LangflowLocalClient
from laomedo.workflow_run_store import WorkflowRunStore


def _digest(value):
    return "sha256:" + sha256(json.dumps(value, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--restart-langflow", action="store_true",
                        help="Use a private SQLite mount and restart the disposable server")
    parser.add_argument("--reopen-host", action="store_true",
                        help="Read the private host binding in a fresh process")
    args = parser.parse_args()
    if args.reopen_host:
        host_db = args.state.expanduser().resolve() / "join.sqlite3"
        with sqlite3.connect(host_db.as_uri() + "?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            rows = [dict(row) for row in db.execute("""SELECT
                c.client_request_id,c.run_id,c.invocation_id,c.flow_id,
                c.graph_run_id,r.trace_id,r.status,r.dispatch_attempts,
                w.runner_request_id,w.runner_request_hash,w.runner_run_id,
                w.runner_provider,w.runner_raw_event_ref
                FROM langflow_client_requests c JOIN runs r ON r.run_id=c.run_id
                JOIN workflow_invocations w ON w.invocation_id=c.invocation_id""")]
        print(json.dumps(rows))
        return
    state = _private_empty(args.state)
    (state / "langflow-data").mkdir()
    bridge_token, runner_token = uuid4().hex, uuid4().hex
    bridge_token_path = state / "bridge-token"
    runner_token_path = state / "runner-token"
    bridge_token_path.write_text(bridge_token, encoding="ascii")
    runner_token_path.write_text(runner_token, encoding="ascii")
    ui_port, bridge_port, runner_port = _port(), _port(), _port()
    started, cancelled = threading.Event(), threading.Event()
    records = {}
    events = []
    lock = threading.RLock()

    class FakeRunner(BaseHTTPRequestHandler):
        def log_message(self, *_):
            return

        def respond(self, code, value):
            data = json.dumps(value).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            if self.headers.get("Authorization") != "Bearer " + runner_token:
                self.respond(401, {"error_category": "unauthorized"})
                return False
            return True

        def do_POST(self):
            if not self.authorized():
                return
            path = urlsplit(self.path).path
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length)) if length else {}
            with lock:
                if path == "/v1/runs/async":
                    request_id = body["request_id"]
                    digest = _digest({key: value for key, value in body.items()
                                      if key != "request_id"})
                    if request_id in records:
                        record = records[request_id]
                        if record["request_hash"] != digest:
                            self.respond(409, {"error_category": "request_identity_conflict"})
                            return
                    else:
                        run_id = str(uuid4())
                        record = {"client_request_id": request_id,
                                  "request_hash": digest, "provider": "codex",
                                  "run_id": run_id, "status": "running",
                                  "raw_event_ref": f"laomedo:run:{run_id}:events",
                                  "cancel_requested": False,
                                  "cancel_confirmed": False}
                        records[request_id] = record
                        events.append({"kind": "start", "run_id": run_id,
                                       "request_id": request_id, "at": time.time()})
                        started.set()
                    self.respond(202, record)
                    return
                parts = path.strip("/").split("/")
                if len(parts) == 4 and parts[:2] == ["v1", "runs"] and parts[3] == "cancel":
                    found = next((item for item in records.values()
                                  if item["run_id"] == parts[2]), None)
                    if found is None:
                        self.respond(404, {"error_category": "unknown_run"})
                        return
                    found.update(status="cancelled", cancel_requested=True,
                                 cancel_confirmed=True)
                    events.append({"kind": "cancel", "run_id": parts[2],
                                   "at": time.time()})
                    cancelled.set()
                    self.respond(202, found)
                    return
            self.respond(404, {"error_category": "unknown_route"})

        def do_GET(self):
            if not self.authorized():
                return
            parts = urlsplit(self.path).path.strip("/").split("/")
            with lock:
                if len(parts) == 3 and parts[:2] == ["v1", "requests"]:
                    found = records.get(parts[2])
                elif len(parts) == 3 and parts[:2] == ["v1", "runs"]:
                    found = next((item for item in records.values()
                                  if item["run_id"] == parts[2]), None)
                else:
                    found = None
                self.respond(200 if found else 404,
                             found or {"error_category": "not_found"})

    runner = ThreadingHTTPServer(("127.0.0.1", runner_port), FakeRunner)
    runner_thread = threading.Thread(target=runner.serve_forever, daemon=True)
    runner_thread.start()
    name = "laomedo-g-join-" + uuid4().hex[:12]
    bridge = None
    browser = None
    teardown = {"langflow_absent": None, "bridge_stopped": None,
                "fake_runner_stopped": None}
    try:
        command = ["docker", "run", "-d", "--rm", "--pull=never", "--name", name,
                   "-p", f"127.0.0.1:{ui_port}:7860", "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges",
                   "--mount", f"type=bind,source={ROOT / 'components'},target=/app/custom_components,readonly",
                   "--mount", f"type=bind,source={bridge_token_path},target=/run/secrets/laomedo-bridge-token,readonly",
                   "-e", "LANGFLOW_COMPONENTS_PATH=/app/custom_components",
                   "-e", "LANGFLOW_AUTO_LOGIN=true", "-e", "DO_NOT_TRACK=true",
                   LANGFLOW_IMAGE]
        if args.restart_langflow:
            command[-1:-1] = ["--mount", f"type=bind,source={state / 'langflow-data'},target=/app/data",
                              "-e", "LANGFLOW_DATABASE_URL=sqlite:////app/data/langflow.db"]
        else:
            command[-1:-1] = ["--mount", f"type=bind,source={state / 'langflow-data'},target=/app/langflow"]
        if subprocess.run(command, capture_output=True, timeout=30).returncode:
            raise RuntimeError("disposable_langflow_start_failed")
        _wait_ui(ui_port)
        bridge = build_service(
            store_path=state / "join.sqlite3",
            bridge_token_file=bridge_token_path,
            runner_token_file=runner_token_path,
            langflow_url=f"http://127.0.0.1:{ui_port}",
            runner_url=f"http://127.0.0.1:{runner_port}", port=bridge_port)
        bridge_thread = threading.Thread(target=bridge.serve_forever, daemon=True)
        bridge_thread.start()
        browser_args = ["node", str(BROWSER), "prepare", str(state),
                        str(ui_port), str(bridge_port), "sha256:" + "0" * 64]
        env = {**os.environ, "PHASE_G_JOIN": "1", "PHASE_E_FAKE_PREFLIGHT": "1"}
        prepared = subprocess.run(browser_args, cwd=ROOT, env=env,
                                  capture_output=True, text=True, timeout=90)
        if prepared.returncode:
            raise RuntimeError("playground_prepare_failed:" +
                               prepared.stdout[-500:])
        browser_args[2] = "run"
        with (state / "browser.log").open("w", encoding="utf-8") as log:
            browser = subprocess.Popen(browser_args, cwd=ROOT, env=env,
                                       stdout=log, stderr=subprocess.STDOUT)
        if not started.wait(65):
            raise RuntimeError("playground_did_not_start_native_fake")
        (state / "stop-now.signal").write_text("stop", encoding="ascii")
        if cancelled.wait(30):
            (state / "runner-terminal.signal").write_text("terminal", encoding="ascii")
        browser.wait(timeout=55)
        observation = json.loads((state / "browser-run.json").read_text())
        flow_id = (state / "flow-id.txt").read_text(encoding="ascii").strip()
        store = WorkflowRunStore(state / "join.sqlite3")
        with store._database() as db:
            bindings = [dict(row) for row in db.execute(
                "SELECT * FROM langflow_client_requests")]
        traces = [store.trace_snapshot(row["run_id"]) for row in bindings]
        native = next(iter(records.values()), None)
        restart = None
        if args.restart_langflow:
            starts_before_restart = sum(item["kind"] == "start" for item in events)
            bridge.shutdown()
            bridge.server_close()
            bridge_thread.join(timeout=3)
            if bridge_thread.is_alive():
                raise RuntimeError("first_host_bridge_not_stopped")
            bridge = None
            teardown["bridge_stopped"] = True
            if not _remove_ui(name):
                raise RuntimeError("first_langflow_container_not_removed")
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
                [sys.executable, "-m", "experiments.exp22.phase_g_join_installed",
                 "--state", str(state), "--reopen-host"],
                cwd=ROOT, capture_output=True, text=True, timeout=20, check=True)
            host_rows = json.loads(reopened.stdout)
            if len(bindings) != 1 or len(host_rows) != 1 or not bindings[0]["graph_run_id"]:
                raise RuntimeError("private_host_binding_missing")
            graph_id = bindings[0]["graph_run_id"]
            with sqlite3.connect(snapshot_path.as_uri() + "?mode=ro", uri=True) as db:
                trace_ids = [row[0] for row in db.execute("""SELECT DISTINCT s.trace_id
                    FROM span s JOIN trace t ON t.id=s.trace_id
                    WHERE t.flow_id=? AND
                    (instr(CAST(s.inputs AS TEXT),?)>0 OR
                     instr(CAST(s.outputs AS TEXT),?)>0)""",
                    (UUID(flow_id).hex, graph_id, graph_id))]
            restart = {"saved_flow_reopened": fetched.get("id") == flow_id,
                       "one_correlated_langflow_trace": len(trace_ids) == 1,
                       "trace_id_present": bool(trace_ids and trace_ids[0]),
                       "host_binding_reopened_in_child": bool(native and traces and all(
                           host_rows[0][key] == bindings[0][key]
                           for key in ("client_request_id", "run_id", "invocation_id",
                                       "flow_id", "graph_run_id")) and
                           host_rows[0]["trace_id"] == traces[0]["trace_id"] and
                           host_rows[0]["runner_request_hash"] ==
                           traces[0]["invocation"]["runner_request_hash"] and
                           host_rows[0]["runner_run_id"] == native["run_id"]
                           and host_rows[0]["runner_request_id"] == events[0]["request_id"]
                           and host_rows[0]["runner_raw_event_ref"] == native["raw_event_ref"]
                           and host_rows[0]["runner_provider"] == "codex"
                           and host_rows[0]["status"] == "cancelled"
                           and host_rows[0]["dispatch_attempts"] == 1),
                       "correlation_basis": "reported_graph_id_in_span_payload_with_trace_fk",
                       "executing_graph_attested": False,
                       "native_starts_total": sum(
                           item["kind"] == "start" for item in events),
                       "native_starts_after_restart": sum(
                           item["kind"] == "start" for item in events) -
                           starts_before_restart}
            (state / "restart-summary.json").write_text(
                json.dumps(restart, indent=2) + "\n", encoding="utf-8")
        cancel_event = next((item for item in events if item["kind"] == "cancel"), None)
        click = observation.get("stop_click_begin_epoch")
        close = observation.get("context_close_begin_epoch")
        summary = {"model_turns": 0, "browser_send_clicked": observation.get("send_clicked"),
                   "browser_stop_clicked": observation.get("stop_clicked"),
                   "native_fake_starts": sum(item["kind"] == "start" for item in events),
                   "native_fake_cancels": sum(item["kind"] == "cancel" for item in events),
                   "one_host_binding": len(bindings) == 1,
                   "same_flow": len(bindings) == 1 and bindings[0]["flow_id"] == flow_id,
                   "native_binding_matches": len(bindings) == 1 and
                       bindings[0]["invocation_id"] == events[0]["request_id"] if events else False,
                   "request_digest_matches": bool(traces and native and
                       traces[0]["invocation"]["runner_request_hash"] ==
                       native["request_hash"]),
                   "stop_cancel_before_close": bool(click and close and cancel_event and
                       click <= cancel_event["at"] < close),
                   "host_terminal": traces[0]["run_status"] if traces else None,
                   "host_trace_reopened": bool(traces),
                   "executing_graph_verified": False,
                   "langflow_restart_tested": args.restart_langflow,
                   "restart": restart}
        (state / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary, sort_keys=True))
        if not all(summary[key] for key in (
                "browser_send_clicked", "browser_stop_clicked", "one_host_binding",
                "same_flow", "native_binding_matches", "request_digest_matches",
                "stop_cancel_before_close", "host_trace_reopened")) or \
                summary["native_fake_starts"] != 1 or \
                summary["native_fake_cancels"] != 1 or \
                summary["host_terminal"] != "cancelled" or \
                (args.restart_langflow and not (
                    restart["saved_flow_reopened"] and
                    restart["one_correlated_langflow_trace"] and
                    restart["trace_id_present"] and
                    restart["host_binding_reopened_in_child"] and
                    restart["native_starts_total"] == 1 and
                    restart["native_starts_after_restart"] == 0)):
            raise RuntimeError("installed_join_probe_failed")
    finally:
        if browser and browser.poll() is None:
            browser.terminate()
            browser.wait(timeout=10)
        if bridge:
            bridge.shutdown()
            bridge.server_close()
            bridge_thread.join(timeout=3)
            teardown["bridge_stopped"] = not bridge_thread.is_alive()
        runner.shutdown()
        runner.server_close()
        runner_thread.join(timeout=3)
        teardown["fake_runner_stopped"] = not runner_thread.is_alive()
        teardown["langflow_absent"] = _remove_ui(name)
        (state / "teardown.json").write_text(json.dumps(teardown, indent=2) + "\n")


if __name__ == "__main__":
    main()
