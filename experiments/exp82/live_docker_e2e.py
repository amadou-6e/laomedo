"""Zero-model local launch: live GitHub read, saved-flow API, Docker stage."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib import request

from laomedo.work_graph.github import fetch
from laomedo.work_graph.grants import LocalGrantAuthority
from laomedo.work_graph.launch import launch_github_docker_saved_flow_stage
from laomedo.workflow_run_store import WorkflowRunStore

from .docker_stage_probe import ROOT, no_model_flow


BASE = os.environ.get("LAOMEDO_EXP82_LANGFLOW_BASE", "http://127.0.0.1:17874")
REPOSITORY = "amadou-6e/laomedo"
ISSUE_NUMBER = 82


def main():
    token = json.load(request.urlopen(BASE + "/api/v1/auto_login", timeout=15))[
        "access_token"]

    def api(method, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = request.Request(BASE + path, data=body, method=method,
            headers={"Authorization": "Bearer " + token,
                     "Content-Type": "application/json", "Accept": "application/json"})
        with request.urlopen(req, timeout=30) as response:
            return json.load(response)

    flow = api("POST", "/api/v1/flows/", no_model_flow())
    flow_id = flow["id"]
    frozen = fetch(REPOSITORY)
    if not frozen.source_complete:
        raise RuntimeError("live_work_graph_incomplete")
    selected = next(item for item in frozen.items if item.number == ISSUE_NUMBER)
    with TemporaryDirectory(prefix="laomedo82-live-") as directory:
        private = Path(directory)
        authority = LocalGrantAuthority(private / "grants.sqlite")
        grant_ref = authority.issue(work_key=selected.key,
            graph_snapshot=frozen,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            timeout_seconds=30, max_turns=0)
        store = WorkflowRunStore(private / "runs.sqlite3")
        stage_input = {"input_value": "TASK"}
        record, output = launch_github_docker_saved_flow_stage(
            frozen=frozen, work_key=selected.key, flow_id=flow_id,
            fetch_export=lambda selected_id: api("GET", "/api/v1/flows/" + selected_id),
            store=store, grant_ref=grant_ref, grant_authority=authority,
            resolved_config={"mode": "no-model"},
            inputs=[stage_input], types=["chat"], outputs=["ChatOutput-exp03"],
            source_root=ROOT)
        config = json.loads(record["resolved_config"])
        trigger = json.loads(record["trigger_json"])
        passed = all((record["status"] == "completed",
            record["dispatch_attempts"] == 1,
            "TASK|BEFORE" in output,
            config["effective_limits"]["max_turns"] == 0,
            config["stage_image"].startswith("langflowai/langflow@sha256:"),
            trigger["work_snapshot"]["key"] == selected.key,
            bool(trigger["authorization_graph_snapshot_id"]),
            token not in record["resolved_config"],
            store.counters()["runs"] == 1))
        report = {"result": "pass" if passed else "fail",
                  "source_complete": frozen.source_complete,
                  "saved_flow_api": "GET /api/v1/flows/{id}",
                  "worker_network": "none",
                  "dispatch_attempts": record["dispatch_attempts"],
                  "run_status": record["status"],
                  "output_marker": "TASK|BEFORE" in output,
                  "grant_max_turns": config["effective_limits"]["max_turns"],
                  "graph_revision_present": bool(record["graph_revision"]),
                  "component_revision_count": len(record["component_revisions"]),
                  "grant_store_outside_git": not (ROOT in private.parents)}
        print(json.dumps(report, sort_keys=True))
        if not passed:
            raise RuntimeError("live_docker_e2e_failed")


if __name__ == "__main__":
    main()
