"""Exercise client disconnect and backend death against pinned Langflow."""

from copy import deepcopy
import http.client
import json
from pathlib import Path
import socket
import subprocess
from threading import Thread
import time
from urllib import request


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
NAME = "laomedo-exp06-20261002"
VOLUME = NAME
IMAGE = "langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0"
BASE = "http://127.0.0.1:17866"
TOKEN = None


def docker(*args, check=True):
    result = subprocess.run(["docker", *args], capture_output=True, text=True,
                            timeout=35, check=False)
    if check and result.returncode:
        raise RuntimeError(f"docker {args[0]} failed: {result.stderr[-400:]}")
    return result.stdout.strip()


def api(method, path, payload=None):
    global TOKEN
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    req = request.Request(BASE + path, data=data, headers=headers, method=method)
    with request.urlopen(req, timeout=30) as response:
        return json.load(response)


def start_request(flow_id):
    conn = http.client.HTTPConnection("127.0.0.1", 17866, timeout=130)
    payload = json.dumps({"input_value": "TASK", "input_type": "chat",
                          "output_type": "chat"}).encode("utf-8")
    conn.request("POST", "/api/v1/run/session/" + flow_id, body=payload,
                 headers={"Content-Type": "application/json",
                          "Authorization": "Bearer " + TOKEN})
    outcome = {}

    def receive():
        try:
            response = conn.getresponse()
            outcome["status"] = response.status
            outcome["body"] = response.read().decode("utf-8", errors="replace")[-500:]
        except (OSError, http.client.HTTPException) as exc:
            outcome["disconnect_error"] = type(exc).__name__

    thread = Thread(target=receive, daemon=True)
    thread.start()
    return conn, thread, outcome


def wait_entered(mode):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if docker("exec", NAME, "test", "-f", "/state/entered-" + mode, check=False) == "":
            # test emits no output both for success and failure; read by cat instead.
            run_id = docker("exec", NAME, "cat", "/state/entered-" + mode, check=False)
            if len(run_id) == 36:
                return run_id
        time.sleep(0.25)
    raise TimeoutError(f"EXP-06 {mode} stage did not enter")


def inspect(run_id):
    return json.loads(docker("exec", NAME, "python",
                             "/experiments/exp06/inspect_store.py", run_id))


def wait_health():
    deadline = time.monotonic() + 75
    while time.monotonic() < deadline:
        try:
            with request.urlopen(BASE + "/health", timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    raise TimeoutError("EXP-06 server did not restart")


def start_backend():
    docker("run", "-d", "--name", NAME, "--network", "bridge", "-p",
           "127.0.0.1:17866:7860", "-e", "PYTHONPATH=/laomedo-src",
           "-e", "LANGFLOW_AUTO_LOGIN=true",
           "-e", "LANGFLOW_DATABASE_URL=sqlite:////state/langflow.db",
           "-v", f"{VOLUME}:/state",
           "-v", f"{ROOT / 'experiments'}:/experiments:ro",
           "-v", f"{ROOT / 'laomedo'}:/laomedo-src/laomedo:ro",
           "--entrypoint", "python", IMAGE, "/experiments/exp06/start.py")


def main():
    global TOKEN
    wait_health()
    TOKEN = api("GET", "/api/v1/auto_login")["access_token"]
    base_flow = json.loads((HERE / "flow.json").read_text(encoding="utf-8"))
    ui_flow = api("POST", "/api/v1/flows/", base_flow)
    crash_flow = deepcopy(base_flow)
    crash_flow["name"] = "EXP-06 synthetic backend death"
    stage = next(n for n in crash_flow["data"]["nodes"] if n["id"] == "Exp06Stage-exp06")
    stage["data"]["node"]["template"]["mode"]["value"] = "crash"
    crash_flow = api("POST", "/api/v1/flows/", crash_flow)

    ui_conn, ui_thread, ui_response = start_request(ui_flow["id"])
    ui_run_id = wait_entered("ui")
    ui_at_close = inspect(ui_run_id)
    if ui_conn.sock:
        ui_conn.sock.shutdown(socket.SHUT_RDWR)
    ui_conn.close()
    ui_thread.join(5)
    TOKEN = api("GET", "/api/v1/auto_login")["access_token"]
    reopened_flow = api("GET", "/api/v1/flows/" + ui_flow["id"])
    docker("exec", NAME, "touch", "/state/release-ui")
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline and inspect(ui_run_id)["status"] != "completed":
        time.sleep(0.25)
    ui_after_release = inspect(ui_run_id)

    crash_conn, crash_thread, crash_response = start_request(crash_flow["id"])
    crash_run_id = wait_entered("crash")
    crash_before_kill = inspect(crash_run_id)
    before_kill_container = docker("inspect", "--format", "{{.State.Status}}", NAME)
    docker("kill", NAME)
    crash_thread.join(5)
    crash_conn.close()
    after_kill_container = docker("inspect", "--format", "{{.State.Status}}", NAME)
    docker("rm", NAME)
    start_backend()
    wait_health()
    crash_after_restart = inspect(crash_run_id)
    ui_after_restart = inspect(ui_run_id)
    startup_log = docker("logs", NAME)
    report = {"image": IMAGE, "ui": {"run_id": ui_run_id,
              "at_client_close": ui_at_close, "reopened_flow_id": reopened_flow["id"],
              "after_release": ui_after_release, "client": ui_response},
              "backend_death": {"run_id": crash_run_id,
              "before_kill": crash_before_kill, "container_before": before_kill_container,
              "container_after": after_kill_container, "after_restart": crash_after_restart,
              "ui_run_after_restart": ui_after_restart, "client": crash_response,
              "startup_swept_one": "exp06_startup_swept=1" in startup_log}}
    (HERE / "observation.json").write_text(json.dumps(report, indent=2) + "\n",
                                            encoding="utf-8")
    print(json.dumps({"ui_before": ui_at_close["status"],
                      "ui_after": ui_after_release["status"],
                      "backend_before": crash_before_kill["status"],
                      "backend_after": crash_after_restart["status"],
                      "startup_swept_one": report["backend_death"]["startup_swept_one"]}))
    if (ui_after_release["status"] != "completed" or
            crash_after_restart["status"] != "crashed" or
            crash_after_restart["dispatch_attempts"] != 1):
        raise AssertionError("EXP-06 lifecycle expectation failed")


if __name__ == "__main__":
    main()
