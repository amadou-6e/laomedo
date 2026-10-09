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
import subprocess
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4

from experiments.exp22.phase_d_live import LANGFLOW_IMAGE, ROOT, _port, _private_empty
from experiments.exp22.phase_e_ui import BROWSER, _remove_ui, _wait_ui
from laomedo.langflow_join_service import build_service
from laomedo.workflow_run_store import WorkflowRunStore


def _digest(value):
    return "sha256:" + sha256(json.dumps(value, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, type=Path)
    args = parser.parse_args()
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
                   "--mount", f"type=bind,source={state / 'langflow-data'},target=/app/langflow",
                   "-e", "LANGFLOW_COMPONENTS_PATH=/app/custom_components",
                   "-e", "LANGFLOW_AUTO_LOGIN=true", "-e", "DO_NOT_TRACK=true",
                   LANGFLOW_IMAGE]
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
        summary = {"model_turns": 0, "browser_send_clicked": observation.get("send_clicked"),
                   "browser_stop_clicked": observation.get("stop_clicked"),
                   "native_fake_starts": sum(item["kind"] == "start" for item in events),
                   "native_fake_cancels": sum(item["kind"] == "cancel" for item in events),
                   "one_host_binding": len(bindings) == 1,
                   "same_flow": len(bindings) == 1 and bindings[0]["flow_id"] == flow_id,
                   "native_binding_matches": len(bindings) == 1 and
                       bindings[0]["invocation_id"] == events[0]["request_id"] if events else False,
                   "host_terminal": traces[0]["run_status"] if traces else None,
                   "host_trace_reopened": bool(traces),
                   "executing_graph_verified": False,
                   "langflow_restart_tested": False}
        (state / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary, sort_keys=True))
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
