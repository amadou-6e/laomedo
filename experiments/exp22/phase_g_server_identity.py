"""Inspect pinned Langflow server execution IDs with a fake runner, no model."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import subprocess
import threading
from urllib import request
from uuid import uuid4

from experiments.exp22.phase_d_live import LANGFLOW_IMAGE, ROOT, _port, _private_empty
from experiments.exp22.phase_e_ui import _remove_ui, _wait_ui


def call(url, payload=None, token=None, api_key=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if api_key:
        headers["x-api-key"] = api_key
    req = request.Request(url, headers=headers,
                          data=None if payload is None else json.dumps(payload).encode())
    with request.urlopen(req, timeout=45) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, type=Path)
    args = parser.parse_args()
    state = _private_empty(args.state)
    (state / "langflow-data").mkdir()
    posted = []
    runner_token = uuid4().hex

    class FakeRunner(BaseHTTPRequestHandler):
        def log_message(self, *_):
            return

        def do_POST(self):
            if self.path != "/v1/runs/async" or self.headers.get("Authorization") != "Bearer " + runner_token:
                self.send_error(401)
                return
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length < 65536:
                self.send_error(400)
                return
            payload = json.loads(self.rfile.read(length))
            identity = payload.get("langflow_probe")
            posted.append(identity)
            run_id = str(uuid4())
            response = {"run_id": run_id, "client_request_id": payload["request_id"],
                        "status": "completed", "answer": "identity probe complete",
                        "provider": "codex", "raw_event_ref": f"laomedo:run:{run_id}:events"}
            data = json.dumps(response).encode()
            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    runner_port, ui_port = _port(), _port()
    fake = ThreadingHTTPServer(("127.0.0.1", runner_port), FakeRunner)
    worker = threading.Thread(target=fake.serve_forever, daemon=True)
    worker.start()
    token_file = state / "api-token"
    token_file.write_text(runner_token, encoding="ascii")
    name = "laomedo-phase-g-" + uuid4().hex[:16]
    teardown = {"ui_container_absent": None, "fake_runner_stopped": None}
    try:
        command = ["docker", "run", "-d", "--rm", "--pull=never", "--name", name,
                   "-p", f"127.0.0.1:{ui_port}:7860", "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges",
                   "--mount", f"type=bind,source={ROOT / 'components'},target=/app/custom_components,readonly",
                   "--mount", f"type=bind,source={token_file},target=/run/secrets/laomedo-runner-token,readonly",
                   "--mount", f"type=bind,source={state / 'langflow-data'},target=/app/langflow",
                   "-e", "LANGFLOW_COMPONENTS_PATH=/app/custom_components",
                   "-e", "LANGFLOW_AUTO_LOGIN=true", "-e", "DO_NOT_TRACK=true",
                   "-e", "LAOMEDO_RUNNER_TOKEN_FILE=/run/secrets/laomedo-runner-token",
                   LANGFLOW_IMAGE]
        if subprocess.run(command, capture_output=True, timeout=30).returncode:
            raise RuntimeError("disposable_langflow_start_failed")
        _wait_ui(ui_port)
        base = f"http://127.0.0.1:{ui_port}"
        login = call(base + "/api/v1/auto_login")["access_token"]
        api_key = call(base + "/api/v1/api_key/",
                       {"name": "exp22-phase-g-identity"}, login)["api_key"]
        flow = json.loads((ROOT / "examples/native-codex-node/flow.json").read_text())
        flow["id"] = str(uuid4())
        flow["name"] = "EXP-22 Phase G identity probe"
        agent = next(node for node in flow["data"]["nodes"]
                     if node["data"]["type"] == "LaomedoCodexAgent")
        template = agent["data"]["node"]["template"]
        code = template["code"]["value"]
        marker = '            return endpoint, payload, "POST"'
        prefix, separator, suffix = code.rpartition(marker)
        if not separator:
            raise RuntimeError("component_probe_insertion_missing")
        template["code"]["value"] = (prefix +
            '            payload["langflow_probe"] = {"graph_run_id": self.graph.run_id, '
            '"flow_id": self.graph.flow_id, "stage_id": self._vertex.id}\n' +
            marker + suffix)
        template["runner_url"]["value"] = f"http://host.docker.internal:{runner_port}"
        created = call(base + "/api/v1/flows/", flow, login)
        flow_id = created["id"]
        for _ in range(2):
            call(base + "/api/v1/run/" + flow_id,
                 {"input_value": "Synthetic identity probe", "input_type": "chat",
                  "output_type": "chat"}, login, api_key)
        if len(posted) != 2:
            raise RuntimeError("server_probe_dispatch_count_mismatch")
        ids = [row.get("graph_run_id") for row in posted]
        stages = [row.get("stage_id") for row in posted]
        flows = [row.get("flow_id") for row in posted]
        backup_code = (
            "import sqlite3; "
            "source=sqlite3.connect('file:/app/.venv/lib/python3.14/site-packages/"
            "langflow/langflow.db?mode=ro',uri=True); "
            "target=sqlite3.connect('/tmp/phase-g-identity.db'); "
            "source.backup(target); target.close(); source.close()"
        )
        backup = subprocess.run(["docker", "exec", name, "python", "-c", backup_code],
                                capture_output=True, timeout=20)
        if backup.returncode:
            raise RuntimeError("langflow_database_backup_failed")
        snapshot = state / "langflow-snapshot.db"
        copied = subprocess.run(["docker", "cp", name + ":/tmp/phase-g-identity.db",
                                 str(snapshot)], capture_output=True, timeout=20)
        if copied.returncode:
            raise RuntimeError("langflow_database_copy_failed")
        with sqlite3.connect(snapshot) as db:
            dump = "\n".join(db.iterdump())
        summary = {"model_turns": 0, "dispatches": len(posted),
                   "distinct_graph_run_ids": len(set(ids)) == 2,
                   "graph_run_ids": ids,
                   "stage_ids_same": len(set(stages)) == 1,
                   "flow_ids": flows, "saved_flow_id": flow_id,
                   "graph_run_ids_in_database": [value in dump for value in ids],
                   "saved_flow_id_in_database": flow_id in dump}
        (state / "identity-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary))
    finally:
        teardown["ui_container_absent"] = _remove_ui(name)
        fake.shutdown()
        fake.server_close()
        worker.join(timeout=5)
        teardown["fake_runner_stopped"] = not worker.is_alive()
        (state / "teardown.json").write_text(json.dumps(teardown, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
