"""Check that the local Docker stage timeout leaves no live container."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from laomedo.work_graph.docker_stage import DockerLangflowStage
from laomedo.work_graph.github import import_pages
from laomedo.work_graph.grants import LocalGrantAuthority
from laomedo.work_graph.launch import launch_work_stage
from laomedo.workflow_run_store import ExternalOutcomeUnknown, WorkflowRunStore

from .docker_stage_probe import ROOT, no_model_flow


def main():
    flow = no_model_flow()
    marker = next(node for node in flow["data"]["nodes"]
                  if node["id"] == "Exp03Marker-exp03")
    code = marker["data"]["node"]["template"]["code"]
    original = code["value"]
    code["value"] = original.replace("        return Message(text=",
        "        time.sleep(5)\n        return Message(text=")
    if code["value"] == original:
        raise RuntimeError("timeout_fixture_not_modified")
    corpus = json.loads((ROOT / "experiments" / "exp16" / "corpus.json")
                        .read_text(encoding="utf-8"))
    frozen = import_pages("verify/exp16", corpus["base"])
    selected = "github:S-20"
    with TemporaryDirectory(prefix="laomedo82-timeout-") as directory:
        private = Path(directory)
        authority = LocalGrantAuthority(private / "grants.sqlite")
        grant_ref = authority.issue(work_key=selected,
            graph_snapshot=frozen,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            timeout_seconds=1, max_turns=0)
        store = WorkflowRunStore(private / "runs.sqlite3")
        stage = DockerLangflowStage(flow, source_root=ROOT)
        timed_out = False
        try:
            launch_work_stage(frozen=frozen, source_fetch=lambda _repo: frozen,
                work_key=selected, stage=stage, store=store, grant_ref=grant_ref,
                grant_authority=authority, resolved_config={"mode": "no-model"},
                inputs=[{"input_value": "TASK"}], types=["chat"],
                outputs=["ChatOutput-exp03"])
        except ExternalOutcomeUnknown:
            timed_out = True
        record = store.get(stage.last_run_id)
        name = stage.last_command[stage.last_command.index("--name") + 1]
        container_absent = subprocess.run(["docker", "inspect", name],
            capture_output=True, timeout=10).returncode != 0
        passed = all((timed_out, record["status"] == "unknown",
                      record["dispatch_attempts"] == 1, container_absent))
        report = {"result": "pass" if passed else "fail",
                  "timeout_observed": timed_out, "run_status": record["status"],
                  "dispatch_attempts": record["dispatch_attempts"],
                  "container_absent": container_absent}
        print(json.dumps(report, sort_keys=True))
        if not passed:
            raise RuntimeError("docker_timeout_boundary_failed")


if __name__ == "__main__":
    main()
