"""Probe outer-client, component HTTP and Langflow server timeout boundaries."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import socket
import subprocess
import sys
import time
from urllib import error, request


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
IMAGE = "langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0"
NAME = "laomedo-exp10-20261005"
BASE = "http://127.0.0.1:17870"
TOKEN = None


def docker(*args: str, check: bool = True) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True,
                            timeout=45, check=False)
    if check and result.returncode:
        raise RuntimeError(f"docker {args[0]} failed: {result.stderr[-400:]}")
    return result.stdout.strip()


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def api(method: str, path: str, payload: dict | None = None, timeout: float = 20) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    req = request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except error.HTTPError as exc:
        if path != "/api/v1/flows/":
            raise
        detail = exc.read().decode("utf-8", errors="replace")[-600:]
        raise RuntimeError(f"EXP-10 setup API {path} returned {exc.code}: {detail}") from None


def wait_health() -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            with request.urlopen(BASE + "/health", timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    raise TimeoutError("EXP-10 Langflow health timeout")


def runner_events() -> list[dict]:
    data = docker("exec", NAME, "cat", "/state/runner-events.jsonl", check=False)
    return [json.loads(line) for line in data.splitlines() if line.startswith("{")]


def wait_for_effect(case: str, seconds: float) -> list[dict]:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        rows = [row for row in runner_events() if row["case"] == case]
        if any(row["event"] == "effect" for row in rows):
            return rows
        time.sleep(0.2)
    return [row for row in runner_events() if row["case"] == case]


def make_flow(case: str, component_timeout: int) -> str:
    flow = deepcopy(json.loads((ROOT / "examples/native-codex-node/flow.json").read_text(encoding="utf-8")))
    flow.pop("id", None)  # Exported example ID is already present in existing databases.
    flow["name"] = f"EXP-10 synthetic {case} timeout"
    flow["description"] = "No model calls; loopback synthetic runner only."
    node = next(node for node in flow["data"]["nodes"]
                if node["data"]["type"] == "LaomedoCodexAgent")
    fields = node["data"]["node"]["template"]
    fields["runner_url"]["value"] = "http://127.0.0.1:18740"
    fields["timeout_seconds"]["value"] = component_timeout
    fields["model"]["value"] = "synthetic"
    fields["effort"]["value"] = "none"
    return api("POST", "/api/v1/flows/", flow)["id"]


def invoke(case: str, flow_id: str, *, route: str, caller_timeout: float) -> dict:
    if route == "v2":
        path = "/api/v2/workflows"
        payload = {"flow_id": flow_id, "input_value": case, "mode": "sync"}
    else:
        path = "/api/v1/run/session/" + flow_id
        payload = {"input_value": case, "input_type": "chat", "output_type": "chat"}
    started = time.monotonic()
    started_utc = utc()
    try:
        body = api("POST", path, payload, caller_timeout)
        outcome = {"kind": "response", "status": 200, "body": body}
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except ValueError:
            body = {"text": raw[-600:]}
        outcome = {"kind": "http_error", "status": exc.code, "body": body}
    except (TimeoutError, socket.timeout, error.URLError, OSError) as exc:
        outcome = {"kind": "client_error", "error_type": type(exc).__name__}
    duration = round(time.monotonic() - started, 3)
    if outcome["kind"] == "response":
        raw = outcome.pop("body")
        outputs = raw.get("outputs", []) if isinstance(raw, dict) else []
        first = outputs[0]["outputs"][0] if outputs else {}
        data = first.get("results", {}).get("message", {}).get("data", {})
        outcome["response"] = {
            "session_id": raw.get("session_id"),
            "graph_run_id": data.get("run_id"),
            "answer": data.get("text"),
        }
    elif outcome["kind"] == "http_error":
        raw = outcome.pop("body")
        detail = raw.get("detail", {}) if isinstance(raw, dict) else {}
        if isinstance(detail, str):
            try:
                detail = json.loads(detail)
            except ValueError:
                detail = {"message": detail[-300:]}
        outcome["response"] = {key: detail.get(key) for key in
                               ("message", "code", "job_id", "timeout_seconds")
                               if detail.get(key) is not None}
    return {"case": case, "route": route, "started_utc": started_utc,
            "duration_seconds": duration, **outcome}


def main() -> dict:
    global TOKEN
    if docker("ps", "-a", "--filter", f"name=^{NAME}$", "--format", "{{.Names}}"):
        raise RuntimeError("EXP-10 disposable container name already in use")
    if docker("volume", "ls", "--filter", f"name=^{NAME}$", "--format", "{{.Name}}"):
        raise RuntimeError("EXP-10 disposable volume name already in use")
    docker("volume", "create", NAME)
    try:
        # The pinned image runs as UID 1000. Initialize the fresh named volume
        # once, without running the long-lived server as root.
        docker("run", "--rm", "--user", "0", "-v", f"{NAME}:/state",
               "--entrypoint", "chown", IMAGE, "1000:0", "/state")
        docker("run", "-d", "--name", NAME, "--network", "bridge", "-p",
               "127.0.0.1:17870:7860", "-e", "LANGFLOW_AUTO_LOGIN=true",
               "-e", "LANGFLOW_DATABASE_URL=sqlite:////state/langflow.db",
               "-e", "LANGFLOW_WORKFLOW_EXECUTION_TIMEOUT=3",
               "-e", "LANGFLOW_DEVELOPER_API_ENABLED=true",
               "-e", "LAOMEDO_RUNNER_TOKEN_FILE=/state/token",
               "-v", f"{NAME}:/state", "-v", f"{ROOT / 'experiments'}:/experiments:ro",
               "--entrypoint", "python", IMAGE, "/experiments/exp10/start.py")
        wait_health()
        TOKEN = api("GET", "/api/v1/auto_login")["access_token"]
        config = {"image": IMAGE, "langflow_version": "1.12.3",
                  "server_timeout_seconds": int(docker("exec", NAME, "python", "-c",
                      "from langflow.services.deps import get_settings_service; "
                      "print(get_settings_service().settings.workflow_execution_timeout)")),
                  "container_status_at_start": docker("inspect", "--format", "{{.State.Status}}", NAME)}
        results = []
        for case, timeout, route, caller_timeout, effect_wait in [
                ("control", 8, "v1", 15, 3),
                ("client", 8, "v1", 1, 6),
                ("component", 2, "v1", 15, 7),
                ("server", 8, "v2", 15, 8)]:
            flow_id = make_flow(case, timeout)
            response = invoke(case, flow_id, route=route, caller_timeout=caller_timeout)
            events = wait_for_effect(case, effect_wait)
            observed = [{"event": row["event"], "utc": row["utc"]} for row in events]
            effect_times = [row["utc"] for row in observed if row["event"] == "effect"]
            caller_end = (datetime.fromisoformat(response["started_utc"]) +
                          timedelta(seconds=response["duration_seconds"]))
            results.append({**response, "configured_component_timeout_seconds": timeout,
                            "configured_caller_timeout_seconds": caller_timeout,
                            "runner_events": observed,
                            "effect_observed": bool(effect_times),
                            "effect_after_caller": bool(effect_times and
                                datetime.fromisoformat(effect_times[0]) > caller_end)})
        report = {"config": config, "cases": results,
                  "container_status_at_end": docker("inspect", "--format", "{{.State.Status}}", NAME)}
        with (HERE / "observation.json").open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
        print(json.dumps({row["case"]: {"kind": row["kind"],
                          "status": row.get("status"),
                          "effect_after_caller": row["effect_after_caller"]}
                          for row in results}, sort_keys=True))
        return report
    finally:
        docker("rm", "-f", NAME, check=False)
        docker("volume", "rm", NAME, check=False)


if __name__ == "__main__":
    if sys.argv[1:] != ["--record"]:
        raise SystemExit("usage: python -m experiments.exp10.probe --record")
    main()
