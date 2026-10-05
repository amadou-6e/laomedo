"""One live Langflow call projected into Laomedo's durable partial trace."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time

from experiments.exp10 import probe as base
from experiments.exp65 import probe as status_probe
from laomedo.workflow_run_store import WorkflowRunStore


HERE = Path(__file__).resolve().parent
NAME = "laomedo-exp66-20261005"
BASE = "http://127.0.0.1:17872"
OFFSETS = (0, 1, 4, 7)


def flow_payload() -> tuple[dict, dict]:
    flow = deepcopy(json.loads((base.ROOT / "examples/native-codex-node/flow.json")
                               .read_text(encoding="utf-8")))
    flow.pop("id", None)
    flow["name"] = "EXP-66 synthetic timeout trace"
    flow["description"] = "No model calls; one loopback runner effect."
    node = next(node for node in flow["data"]["nodes"]
                if node["data"]["type"] == "LaomedoCodexAgent")
    fields = node["data"]["node"]["template"]
    fields["runner_url"]["value"] = "http://127.0.0.1:18740"
    fields["timeout_seconds"]["value"] = 8
    fields["model"]["value"] = "synthetic"
    fields["effort"]["value"] = "none"
    return flow, {node["id"]: fields["code"]["value"]}


def record_new_effect(store, run_id: str, invocation_id: str, seen: set[str]) -> None:
    for row in base.runner_events():
        if row.get("case") != "server" or row.get("event") != "effect":
            continue
        digest = sha256(json.dumps(row, sort_keys=True).encode("utf-8")).hexdigest()
        if digest in seen:
            continue  # Re-reading the same journal row is not another delivery.
        seen.add(digest)
        store.record_effect(run_id, invocation_id, source="exp66-synthetic-runner",
                            source_ref="sha256:" + digest, source_time=row["utc"])


def main() -> dict:
    base.NAME, base.BASE, base.TOKEN = NAME, BASE, None
    status_probe.NAME = NAME
    if base.docker("ps", "-a", "--filter", f"name=^{NAME}$", "--format", "{{.Names}}"):
        raise RuntimeError("EXP-66 disposable container name already in use")
    if base.docker("volume", "ls", "--filter", f"name=^{NAME}$", "--format", "{{.Name}}"):
        raise RuntimeError("EXP-66 disposable volume name already in use")
    base.docker("volume", "create", NAME)
    try:
        base.docker("run", "--rm", "--user", "0", "-v", f"{NAME}:/state",
                    "--entrypoint", "chown", base.IMAGE, "1000:0", "/state")
        base.docker("run", "-d", "--name", NAME, "--network", "bridge", "-p",
                    "127.0.0.1:17872:7860", "-e", "LANGFLOW_AUTO_LOGIN=true",
                    "-e", "LANGFLOW_DATABASE_URL=sqlite:////state/langflow.db",
                    "-e", "LANGFLOW_WORKFLOW_EXECUTION_TIMEOUT=3",
                    "-e", "LANGFLOW_DEVELOPER_API_ENABLED=true",
                    "-e", "LAOMEDO_RUNNER_TOKEN_FILE=/state/token",
                    "-v", f"{NAME}:/state", "-v", f"{base.ROOT / 'experiments'}:/experiments:ro",
                    "--entrypoint", "python", base.IMAGE, "/experiments/exp10/start.py")
        base.wait_health()
        base.TOKEN = base.api("GET", "/api/v1/auto_login")["access_token"]
        server_timeout = int(base.docker("exec", NAME, "python", "-c",
            "from langflow.services.deps import get_settings_service; "
            "print(get_settings_service().settings.workflow_execution_timeout)"))
        if server_timeout != 3:
            raise RuntimeError("effective server timeout differs from frozen protocol")
        clock_before = status_probe.clock_calibration()
        flow, code = flow_payload()
        flow_id = base.api("POST", "/api/v1/flows/", flow)["id"]
        with TemporaryDirectory(prefix="laomedo-exp66-") as directory:
            path = Path(directory) / "runs.sqlite3"
            store = WorkflowRunStore(path)
            run = store.reserve(graph=flow["data"], component_code=code,
                                resolved_config={"flow_id": flow_id, "server_timeout": 3,
                                                 "component_timeout": 8, "caller_timeout": 15},
                                trigger={"type": "direct", "experiment": "EXP-66"})
            run_id = run["run_id"]
            invocation_id = store.reserve_invocation(run_id, "LaomedoCodexAgent-native")
            if store.trace_snapshot(run_id)["dispatch_attempts"] != 0:
                raise RuntimeError("dispatch occurred before durable reservation")
            store.begin_invocation(run_id, invocation_id)
            response = base.invoke("server", flow_id, route="v2", caller_timeout=15)
            response_mono = time.monotonic()
            if response.get("status") != 408 or not response.get("response", {}).get("job_id"):
                raise RuntimeError("frozen timeout case did not return 408 with job ID")
            store.record_timeout(run_id, invocation_id,
                                 http_status=response["status"], detail=response["response"])
            job_id = response["response"]["job_id"]
            seen_effects: set[str] = set()
            snapshots = []
            for offset in OFFSETS:
                due = response_mono + offset
                if due > time.monotonic():
                    time.sleep(due - time.monotonic())
                record_new_effect(store, run_id, invocation_id, seen_effects)
                snapshot = status_probe.status_snapshot(
                    job_id, offset, time.monotonic() - response_mono)
                store.record_job_status(run_id, invocation_id,
                                        http_status=snapshot.get("http_status", 0),
                                        detail={"code": snapshot.get("detail_code"),
                                                "job_id": job_id})
                snapshots.append(snapshot)
            record_new_effect(store, run_id, invocation_id, seen_effects)
            trace_before = store.trace_snapshot(run_id)
            reopened = WorkflowRunStore(path)
            swept = reopened.sweep_crashed()
            trace_after = reopened.trace_snapshot(run_id)
            runner = [{"event": row["event"], "utc": row["utc"]}
                      for row in base.runner_events() if row.get("case") == "server"]
            report = {"config": {"image": base.IMAGE,
                                  "langflow_version": "1.12.3",
                                  "effective_server_timeout_seconds": server_timeout,
                                  "runner_delay_seconds": 6,
                                  "component_timeout_seconds": 8,
                                  "caller_timeout_seconds": 15,
                                  "poll_offsets_seconds": list(OFFSETS)},
                      "clock_before": clock_before,
                      "clock_after": status_probe.clock_calibration(),
                      "caller": response,
                      "status_snapshots": snapshots,
                      "runner_events": runner,
                      "trace_before_reopen": trace_before,
                      "trace_after_reopen": trace_after,
                      "restart_sweep_ids": swept,
                      "container_status": base.docker("inspect", "--format",
                                                      "{{.State.Status}}", NAME)}
            with (HERE / "observation.json").open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(report, stream, indent=2, sort_keys=True)
                stream.write("\n")
            print(json.dumps({"caller_status": response["status"],
                              "job_codes": [row.get("detail_code") for row in snapshots],
                              "effects": len(seen_effects),
                              "trace_state": trace_after["stream_state"],
                              "dispatch_attempts": trace_after["dispatch_attempts"]}))
            return report
    finally:
        base.docker("rm", "-f", NAME, check=False)
        base.docker("volume", "rm", NAME, check=False)


if __name__ == "__main__":
    if sys.argv[1:] != ["--record"]:
        raise SystemExit("usage: python -m experiments.exp66.probe --record")
    main()
