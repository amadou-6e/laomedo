"""One-call, zero-model post-408 Langflow job-status probe."""

from datetime import datetime, timezone
from pathlib import Path
import json
import sys
import time
from urllib import error
from urllib.parse import urlencode

from experiments.exp10 import probe as base


HERE = Path(__file__).resolve().parent
NAME = "laomedo-exp65-20261005"
BASE = "http://127.0.0.1:17871"
OFFSETS = (0, 1, 4, 7)


def clock_calibration() -> dict:
    before = datetime.now(timezone.utc).timestamp()
    container_utc = float(base.docker("exec", NAME, "python", "-c",
                        "import time; print(time.time())"))
    after = datetime.now(timezone.utc).timestamp()
    return {"host_before_utc": before, "container_utc": container_utc,
            "host_after_utc": after, "estimated_offset_seconds":
            round(container_utc - (before + after) / 2, 6),
            "uncertainty_seconds": round((after - before) / 2, 6)}


def status_snapshot(job_id: str, target_offset: int, actual_offset: float) -> dict:
    result = {"target_offset_seconds": target_offset,
              "actual_offset_seconds": round(actual_offset, 3),
              "observed_utc": base.utc()}
    try:
        data = base.api("GET", "/api/v2/workflows?" + urlencode({"job_id": job_id}),
                        timeout=5)
        result["http_status"] = 200
        result["response_keys"] = sorted(data.keys()) if isinstance(data, dict) else []
        if isinstance(data, dict):
            for key in ("object", "status", "job_id", "id", "flow_id", "run_id",
                        "session_id", "created_at", "updated_at", "completed_at"):
                value = data.get(key)
                if isinstance(value, (str, int, float, bool)) or value is None:
                    result[key] = value
            if "error" in data:
                result["error_present"] = data["error"] is not None
                result["error_type"] = type(data["error"]).__name__
            if "outputs" in data:
                result["outputs_present"] = data["outputs"] is not None
        return result
    except error.HTTPError as exc:
        result["http_status"] = exc.code
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw)
            result["response_keys"] = sorted(detail.keys()) if isinstance(detail, dict) else []
            if isinstance(detail, dict):
                result["detail_type"] = type(detail.get("detail")).__name__
        except ValueError:
            result["response_keys"] = []
        return result
    except (TimeoutError, OSError) as exc:
        result["transport_error"] = type(exc).__name__
        return result


def main() -> dict:
    base.NAME, base.BASE, base.TOKEN = NAME, BASE, None
    if base.docker("ps", "-a", "--filter", f"name=^{NAME}$", "--format", "{{.Names}}"):
        raise RuntimeError("EXP-65 disposable container name already in use")
    if base.docker("volume", "ls", "--filter", f"name=^{NAME}$", "--format", "{{.Name}}"):
        raise RuntimeError("EXP-65 disposable volume name already in use")
    base.docker("volume", "create", NAME)
    try:
        base.docker("run", "--rm", "--user", "0", "-v", f"{NAME}:/state",
                    "--entrypoint", "chown", base.IMAGE, "1000:0", "/state")
        base.docker("run", "-d", "--name", NAME, "--network", "bridge", "-p",
                    "127.0.0.1:17871:7860", "-e", "LANGFLOW_AUTO_LOGIN=true",
                    "-e", "LANGFLOW_DATABASE_URL=sqlite:////state/langflow.db",
                    "-e", "LANGFLOW_WORKFLOW_EXECUTION_TIMEOUT=3",
                    "-e", "LANGFLOW_DEVELOPER_API_ENABLED=true",
                    "-e", "LAOMEDO_RUNNER_TOKEN_FILE=/state/token",
                    "-v", f"{NAME}:/state", "-v", f"{base.ROOT / 'experiments'}:/experiments:ro",
                    "--entrypoint", "python", base.IMAGE, "/experiments/exp10/start.py")
        base.wait_health()
        base.TOKEN = base.api("GET", "/api/v1/auto_login")["access_token"]
        server_limit = int(base.docker("exec", NAME, "python", "-c",
            "from langflow.services.deps import get_settings_service; "
            "print(get_settings_service().settings.workflow_execution_timeout)"))
        if server_limit != 3:
            raise RuntimeError("effective server timeout differs from frozen protocol")
        clock_before = clock_calibration()
        flow_id = base.make_flow("server", 8)
        started_mono = time.monotonic()
        outcome = base.invoke("server", flow_id, route="v2", caller_timeout=15)
        response_mono = time.monotonic()
        response = outcome.get("response", {})
        if outcome.get("status") != 408 or not response.get("job_id"):
            snapshots = []  # No identifier: explicit negative result, no second POST.
        else:
            snapshots = []
            for offset in OFFSETS:
                due = response_mono + offset
                if due > time.monotonic():
                    time.sleep(due - time.monotonic())
                snapshots.append(status_snapshot(response["job_id"], offset,
                                                  time.monotonic() - response_mono))
        events = [{"case": row["case"], "event": row["event"], "utc": row["utc"],
                   "container_monotonic_seconds": row["monotonic"]}
                  for row in base.runner_events()]
        report = {"config": {"image": base.IMAGE, "langflow_version": "1.12.3",
                              "server_timeout_seconds": server_limit,
                              "case": "server", "runner_delay_seconds": 6,
                              "component_timeout_seconds": 8,
                              "caller_timeout_seconds": 15,
                              "poll_offsets_seconds": list(OFFSETS)},
                  "clock_before": clock_before, "clock_after": clock_calibration(),
                  "caller": outcome, "host_invocation_monotonic_elapsed_seconds":
                  round(response_mono - started_mono, 3),
                  "status_snapshots": snapshots, "runner_events": events,
                  "container_status": base.docker("inspect", "--format",
                                                  "{{.State.Status}}", NAME)}
        with (HERE / "observation.json").open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
        print(json.dumps({"caller_status": outcome.get("status"),
                          "job_id_present": bool(response.get("job_id")),
                          "poll_http_statuses": [row.get("http_status") for row in snapshots],
                          "effects": sum(row["event"] == "effect" for row in events)}))
        return report
    finally:
        base.docker("rm", "-f", NAME, check=False)
        base.docker("volume", "rm", NAME, check=False)


if __name__ == "__main__":
    if sys.argv[1:] != ["--record"]:
        raise SystemExit("usage: python -m experiments.exp65.probe --record")
    main()
