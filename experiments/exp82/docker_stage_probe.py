"""Credential-free Docker stage smoke check through the host controller."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from laomedo.work_graph.docker_stage import DockerLangflowStage
from laomedo.workflow_run_store import WorkflowRunStore


ROOT = Path(__file__).resolve().parents[2]
FLOW = ROOT / "experiments" / "exp03" / "flow.json"


def no_model_flow():
    flow = deepcopy(json.loads(FLOW.read_text(encoding="utf-8")))
    flow["data"]["nodes"] = [node for node in flow["data"]["nodes"]
                            if node["id"] != "Exp03Pause-exp03"]
    first, second, last = flow["data"]["edges"]
    direct = deepcopy(first)
    direct["id"] = "ChatInput-exp03-Exp03Marker-exp03"
    direct["target"] = "Exp03Marker-exp03"
    direct["data"]["targetHandle"] = second["data"]["targetHandle"]
    direct["targetHandle"] = second["targetHandle"]
    flow["data"]["edges"] = [direct, last]
    return flow


def main():
    with TemporaryDirectory(prefix="laomedo82-stage-") as directory:
        stage = DockerLangflowStage(no_model_flow(), source_root=ROOT)
        store = WorkflowRunStore(Path(directory) / "runs.sqlite3")
        record, output = stage.execute(store,
            resolved_config={"mode": "no-model", "effective_limits": {
                "timeout_seconds": 30, "max_turns": 0}},
            trigger={"type": "fixture"},
            inputs=[{"input_value": "TASK"}], types=["chat"],
            outputs=["ChatOutput-exp03"])
        passed = (record["status"] == "completed" and
                  record["dispatch_attempts"] == 1 and
                  "TASK|BEFORE" in output and
                  record["graph_revision"] == stage.graph_revision and
                  record["component_revisions"] == stage.component_revisions)
        print(json.dumps({"result": "pass" if passed else "fail",
            "status": record["status"],
            "graph_revision_present": bool(record["graph_revision"]),
            "component_revisions": len(record["component_revisions"]),
            "output_marker": "TASK|BEFORE" in output}, sort_keys=True))
        if not passed:
            raise RuntimeError("stage_result_failed")


if __name__ == "__main__":
    main()
