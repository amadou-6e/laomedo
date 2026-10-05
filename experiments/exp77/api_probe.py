"""Credential-free saved-flow API check for the frozen Langflow stage adapter.

Run only against a disposable Langflow 1.12.3 server with auto-login enabled.
The short-lived API token stays in process memory and is never printed.
"""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import time
from urllib import request

from laomedo.langflow_stage_adapter import FrozenLangflowStage
from laomedo.workflow_run_store import WorkflowRunStore


BASE = "http://127.0.0.1:7860"
FLOW = Path("/repo/experiments/exp03/flow.json")


def main():
    token = json.load(request.urlopen(BASE + "/api/v1/auto_login", timeout=15))[
        "access_token"]

    def api(method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = request.Request(BASE + path, data=data, method=method,
            headers={"Authorization": "Bearer " + token,
                     "Content-Type": "application/json", "Accept": "application/json"})
        with request.urlopen(req, timeout=30) as response:
            return json.load(response)

    with TemporaryDirectory(prefix="laomedo77-") as directory:
        root = Path(directory)
        gate = root / "release"
        flow = json.loads(FLOW.read_text(encoding="utf-8"))
        pause = next(node for node in flow["data"]["nodes"]
                     if node["id"] == "Exp03Pause-exp03")
        pause["data"]["node"]["template"]["gate"]["value"] = str(gate)
        created = api("POST", "/api/v1/flows/", flow)
        flow_id = created["id"]
        fetch = lambda selected: api("GET", "/api/v1/flows/" + selected)
        stage = FrozenLangflowStage.from_saved_flow(flow_id, fetch)
        store = WorkflowRunStore(root / "runs.sqlite3")
        observed = {}

        def execute(selected, key):
            try:
                observed[key] = selected.execute(store,
                    resolved_config={"mode": "synthetic-api-test"},
                    trigger={"type": "synthetic-flow", "flow_id": flow_id},
                    inputs=[{"input_value": "TASK"}], types=["chat"],
                    outputs=["ChatOutput-exp03"])
            except Exception as exc:
                observed[key + "_error"] = type(exc).__name__ + ":" + str(exc)

        worker = Thread(target=execute, args=(stage, "first"), daemon=True)
        worker.start()
        deadline = time.monotonic() + 25
        while not gate.with_suffix(".entered").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not gate.with_suffix(".entered").exists():
            gate.write_text("release", encoding="utf-8")
            worker.join(5)
            raise RuntimeError("paused_stage_not_entered: " + repr(observed))
        modified = deepcopy(fetch(flow_id))
        marker = next(node for node in modified["data"]["nodes"]
                      if node["id"] == "Exp03Marker-exp03")
        marker["data"]["node"]["template"]["marker"]["value"] = "AFTER"
        source = marker["data"]["node"]["template"]["code"]["value"]
        changed = source.replace("|{self.marker}", "|API:{self.marker}")
        if changed == source:
            raise RuntimeError("component_code_fixture_not_changed")
        marker["data"]["node"]["template"]["code"]["value"] = changed
        api("PATCH", "/api/v1/flows/" + flow_id, {"data": modified["data"]})
        gate.write_text("release", encoding="utf-8")
        worker.join(25)
        if worker.is_alive() or "first_error" in observed:
            raise RuntimeError("first_stage_failed: " + repr(observed))
        execute(FrozenLangflowStage.from_saved_flow(flow_id, fetch), "second")
        if "second_error" in observed:
            raise RuntimeError("second_stage_failed: " + repr(observed))
        old, old_output = observed["first"]
        new, new_output = observed["second"]
        passed = ("TASK|BEFORE" in str(old_output) and
                  "TASK|API:AFTER" in str(new_output) and
                  old["graph_revision"] != new["graph_revision"] and
                  old["component_revisions"]["Exp03Marker-exp03"] !=
                  new["component_revisions"]["Exp03Marker-exp03"] and
                  store.counters()["dispatch_attempts"] == 2)
        report = {"pinned_runtime": "langflow=1.12.3,lfx=1.12.3",
                  "api_route": "GET /api/v1/flows/{id}",
                  "old_output_marker": "TASK|BEFORE" in str(old_output),
                  "new_output_marker": "TASK|API:AFTER" in str(new_output),
                  "graph_revisions_distinct": old["graph_revision"] != new["graph_revision"],
                  "component_revisions_distinct":
                      old["component_revisions"]["Exp03Marker-exp03"] !=
                      new["component_revisions"]["Exp03Marker-exp03"],
                  "dispatch_attempts": store.counters()["dispatch_attempts"],
                  "result": "pass" if passed else "fail"}
        print(json.dumps(report, sort_keys=True))
        if not passed:
            raise RuntimeError("saved_flow_api_adapter_check_failed")


if __name__ == "__main__":
    main()
