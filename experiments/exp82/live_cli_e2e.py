"""Zero-model test of the installed Work Graph launch command."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib import request

from laomedo.work_graph.github import fetch
from laomedo.work_graph.grants import LocalGrantAuthority
from laomedo.workflow_run_store import WorkflowRunStore

from .docker_stage_probe import no_model_flow


BASE = "http://127.0.0.1:17874"


def main():
    token = json.load(request.urlopen(BASE + "/api/v1/auto_login", timeout=15))[
        "access_token"]
    req = request.Request(BASE + "/api/v1/flows/",
        data=json.dumps(no_model_flow()).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": "application/json"})
    with request.urlopen(req, timeout=30) as response:
        flow_id = json.load(response)["id"]
    frozen = fetch("amadou-6e/laomedo")
    selected = next(item for item in frozen.items if item.number == 82)
    with TemporaryDirectory(prefix="laomedo82-cli-") as directory:
        private = Path(directory)
        snapshot = frozen.save(private / "snapshots")
        grant_path, run_path = private / "grants.sqlite", private / "runs.sqlite3"
        authority = LocalGrantAuthority(grant_path)
        ref = authority.issue(work_key=selected.key,
            graph_snapshot_id=frozen.snapshot_id,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            timeout_seconds=30, max_turns=0)
        command = [sys.executable, "-m", "laomedo.work_graph", "launch",
            str(snapshot), "--work-key", selected.key,
            "--flow-id", flow_id, "--langflow-base", BASE,
            "--grant-store", str(grant_path), "--grant-ref", ref,
            "--run-store", str(run_path), "--task", "TASK"]
        process = subprocess.run(command, capture_output=True, text=True,
                                 encoding="utf-8", timeout=90)
        if process.returncode:
            raise RuntimeError("work_graph_launch_command_failed")
        result = json.loads(process.stdout)
        counters = WorkflowRunStore(run_path).counters()
        passed = (result["status"] == "completed" and
                  result["dispatch_attempts"] == 1 and
                  result["output_present"] and counters["runs"] == 1 and
                  token not in process.stdout and ref not in process.stdout)
        print(json.dumps({"result": "pass" if passed else "fail",
            "source_complete": frozen.source_complete,
            "launch_command": "laomedo-work-graph launch",
            "run_status": result["status"],
            "dispatch_attempts": result["dispatch_attempts"],
            "output_present": result["output_present"],
            "run_identity_present": bool(result["run_id"] and result["trace_id"]),
            "api_token_absent_from_output": token not in process.stdout}, sort_keys=True))
        if not passed:
            raise RuntimeError("work_graph_launch_command_result_failed")


if __name__ == "__main__":
    main()
