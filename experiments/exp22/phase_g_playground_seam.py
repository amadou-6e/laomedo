"""No-model Playground probe for a durable first-call host bridge seam.

The HTTP server is a fake bridge/runner combination. It proves that a visible
Playground Send reaches a host-owned reservation before an emulated start, and
that visible Stop can address the same client UUID. It does not implement the
production bridge or attest the executing Langflow graph.
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
from urllib import error, request
from uuid import uuid4

from experiments.exp22.phase_d_live import LANGFLOW_IMAGE, ROOT, _port, _private_empty
from experiments.exp22.phase_e_ui import BROWSER, _flow_code_pins, _remove_ui, _wait_ui
from laomedo.workflow_run_store import WorkflowRunStore


def _digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return "sha256:" + sha256(encoded).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, type=Path)
    args = parser.parse_args()
    _flow_code_pins()
    state = _private_empty(args.state)
    (state / "langflow-data").mkdir()
    token = uuid4().hex
    token_path = state / "bridge-token"
    token_path.write_text(token, encoding="ascii")
    store = WorkflowRunStore(state / "join.sqlite3")
    seen = {}
    calls = []
    lock = threading.RLock()

    class FakeBridge(BaseHTTPRequestHandler):
        def log_message(self, *_):
            return

        def respond(self, status, body):
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            if self.headers.get("Authorization") != "Bearer " + token:
                self.respond(401, {"error_category": "unauthorized"})
                return False
            return True

        def do_POST(self):
            if not self.authorized():
                return
            if self.path == "/v1/runs/async":
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    self.respond(400, {"error_category": "invalid_body"})
                    return
                body = json.loads(self.rfile.read(length))
                client_id = body.get("request_id")
                canonical = {key: value for key, value in body.items()
                             if key != "request_id"}
                body_hash = _digest(canonical)
                with lock:
                    if client_id in seen:
                        existing = seen[client_id]
                        if existing["request_hash"] != body_hash:
                            self.respond(409, {"error_category": "request_identity_conflict"})
                            return
                        calls.append("duplicate_client_lookup")
                    else:
                        flow = json.loads((ROOT / "examples/native-codex-node/flow.json").read_text(
                            encoding="utf-8"))
                        codes = {node["id"]: node["data"]["node"]["template"]["code"]["value"]
                                 for node in flow["data"]["nodes"]}
                        run = store.reserve(graph=flow["data"], component_code=codes,
                                            resolved_config=canonical,
                                            trigger={"kind": "visible_playground_probe"})
                        invocation_id = store.reserve_invocation(
                            run["run_id"], "LaomedoCodexAgent-native")
                        store.freeze_runner_request(run["run_id"], invocation_id,
                                                    body_hash)
                        # This emulates the host's committed attempt boundary. No
                        # actual runner POST or model call occurs in this probe.
                        store.begin_invocation(run["run_id"], invocation_id)
                        native_run_id = str(uuid4())
                        store.bind_runner_ack(
                            run["run_id"], invocation_id, request_id=invocation_id,
                            provider="codex", runner_run_id=native_run_id,
                            raw_event_ref=f"laomedo:run:{native_run_id}:events")
                        seen[client_id] = {"client_id": client_id,
                            "body": body,
                            "request_hash": body_hash, "laomedo_run_id": run["run_id"],
                            "invocation_id": invocation_id, "run_id": native_run_id,
                            "status": "running", "cancel_confirmed": False}
                        calls.append("durable_binding_before_emulated_start")
                    item = seen[client_id]
                    self.respond(202, {"run_id": item["run_id"],
                        "client_request_id": client_id, "status": item["status"],
                        "provider": "codex", "raw_event_ref":
                        f"laomedo:run:{item['run_id']}:events"})
                return
            parts = self.path.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["v1", "runs"] and parts[3] == "cancel":
                with lock:
                    matches = [item for item in seen.values() if item["run_id"] == parts[2]]
                    if len(matches) != 1:
                        self.respond(404, {"error_category": "unknown_run"})
                        return
                    item = matches[0]
                    item["status"] = "cancelled"
                    item["cancel_confirmed"] = True
                    store.record_runner_observation(
                        item["laomedo_run_id"], item["invocation_id"],
                        provider="codex", runner_run_id=item["run_id"],
                        kind="runner_cancel",
                        payload={"cancel_requested": True, "cancel_confirmed": True})
                    calls.append("exact_cancel")
                    self.respond(202, {"run_id": item["run_id"],
                                       "status": "cancelled", "cancel_confirmed": True})
                return
            self.respond(404, {"error_category": "unknown_route"})

        def do_GET(self):
            if not self.authorized():
                return
            parts = self.path.strip("/").split("/")
            with lock:
                if len(parts) == 3 and parts[:2] == ["v1", "requests"]:
                    item = seen.get(parts[2])
                    if item is None:
                        self.respond(404, {"error_category": "unknown_request"})
                        return
                    calls.append("client_request_lookup")
                    self.respond(200, {"run_id": item["run_id"],
                        "client_request_id": item["client_id"],
                        "request_hash": item["request_hash"],
                        "status": item["status"]})
                    return
                if len(parts) == 3 and parts[:2] == ["v1", "runs"]:
                    matches = [item for item in seen.values() if item["run_id"] == parts[2]]
                    if len(matches) != 1:
                        self.respond(404, {"error_category": "unknown_run"})
                        return
                    item = matches[0]
                    self.respond(200, {"run_id": item["run_id"],
                        "status": item["status"],
                        "cancel_confirmed": item["cancel_confirmed"]})
                    return
            self.respond(404, {"error_category": "unknown_route"})

    bridge_port, ui_port = _port(), _port()
    bridge = ThreadingHTTPServer(("127.0.0.1", bridge_port), FakeBridge)
    bridge_thread = threading.Thread(target=bridge.serve_forever, daemon=True)
    bridge_thread.start()
    name = "laomedo-phase-g-seam-" + uuid4().hex[:16]
    browser = None
    teardown = {"ui_container_absent": None, "fake_bridge_stopped": None}
    try:
        command = ["docker", "run", "-d", "--rm", "--pull=never", "--name", name,
                   "-p", f"127.0.0.1:{ui_port}:7860", "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges",
                   "--mount", f"type=bind,source={ROOT / 'components'},target=/app/custom_components,readonly",
                   "--mount", f"type=bind,source={token_path},target=/run/secrets/laomedo-runner-token,readonly",
                   "--mount", f"type=bind,source={state / 'langflow-data'},target=/app/langflow",
                   "-e", "LANGFLOW_COMPONENTS_PATH=/app/custom_components",
                   "-e", "LANGFLOW_AUTO_LOGIN=true", "-e", "DO_NOT_TRACK=true",
                   "-e", "LAOMEDO_RUNNER_TOKEN_FILE=/run/secrets/laomedo-runner-token",
                   LANGFLOW_IMAGE]
        if subprocess.run(command, capture_output=True, timeout=30).returncode:
            raise RuntimeError("disposable_langflow_start_failed")
        _wait_ui(ui_port)
        browser_args = ["node", str(BROWSER), "prepare", str(state),
                        str(ui_port), str(bridge_port), "sha256:" + "0" * 64]
        prepared = subprocess.run(browser_args, cwd=ROOT, capture_output=True,
                                  text=True, timeout=90)
        if prepared.returncode:
            raise RuntimeError("playground_prepare_failed")
        browser_args[2] = "run"
        browser_env = dict(os.environ)
        browser_env["PHASE_E_FAKE_PREFLIGHT"] = "1"
        browser_log = (state / "browser.log").open("w", encoding="utf-8")
        browser = subprocess.Popen(browser_args, cwd=ROOT, env=browser_env,
                                   stdout=browser_log, stderr=subprocess.STDOUT)
        browser_log.close()
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and not seen and browser.poll() is None:
            time.sleep(.1)
        if not seen:
            raise RuntimeError("playground_did_not_reach_fake_bridge")
        (state / "stop-now.signal").write_text("stop", encoding="ascii")
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline and "exact_cancel" not in calls:
            if browser.poll() is not None:
                break
            time.sleep(.1)
        if "exact_cancel" in calls:
            (state / "runner-terminal.signal").write_text("terminal", encoding="ascii")
        browser.wait(timeout=50)
        observation = json.loads((state / "browser-run.json").read_text(encoding="utf-8"))
        item = next(iter(seen.values()))
        start_url = f"http://127.0.0.1:{bridge_port}/v1/runs/async"

        def replay(body):
            value = request.Request(start_url, data=json.dumps(body).encode("utf-8"),
                headers={"Authorization": "Bearer " + token,
                         "Content-Type": "application/json"}, method="POST")
            try:
                with request.urlopen(value, timeout=10) as response:
                    return response.status
            except error.HTTPError as exc:
                return exc.code

        duplicate_status = replay(item["body"])
        changed = {**item["body"], "task": "different synthetic request"}
        conflict_status = replay(changed)
        saved = WorkflowRunStore(store.path).trace_snapshot(item["laomedo_run_id"])
        result = {"model_turns": 0, "client_requests": len(seen),
                  "emulated_runner_starts": calls.count("durable_binding_before_emulated_start"),
                  "persisted_before_start": calls[:1] == ["durable_binding_before_emulated_start"],
                  "same_body_retry_status": duplicate_status,
                  "changed_body_retry_status": conflict_status,
                  "client_and_invocation_ids_differ": item["client_id"] != item["invocation_id"],
                  "browser_send_clicked": observation.get("send_clicked"),
                  "browser_stop_clicked": observation.get("stop_clicked"),
                  "client_uuid_lookup_seen": "client_request_lookup" in calls,
                  "exact_cancel_seen": "exact_cancel" in calls,
                  "host_trace_reopened": saved["invocation"]["runner_run_id"] == item["run_id"],
                  "cancel_receipt_reopened": any(
                      row["kind"] == "runner_cancel" for row in saved["receipts"]),
                  "langflow_graph_attested": False,
                  "langflow_restart_tested": False}
        result["passed"] = all(result[key] for key in (
            "persisted_before_start", "browser_send_clicked", "browser_stop_clicked",
            "client_uuid_lookup_seen", "exact_cancel_seen", "host_trace_reopened",
            "cancel_receipt_reopened", "client_and_invocation_ids_differ")) and (
                duplicate_status == 202 and conflict_status == 409 and
                result["emulated_runner_starts"] == 1)
        (state / "sanitized.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))
        if not result["passed"]:
            raise RuntimeError("playground_seam_probe_failed")
    finally:
        if browser and browser.poll() is None:
            browser.terminate()
            browser.wait(timeout=10)
        teardown["ui_container_absent"] = _remove_ui(name)
        bridge.shutdown()
        bridge.server_close()
        bridge_thread.join(timeout=5)
        teardown["fake_bridge_stopped"] = not bridge_thread.is_alive()
        (state / "teardown.json").write_text(json.dumps(teardown, indent=2),
                                               encoding="utf-8")


if __name__ == "__main__":
    main()
