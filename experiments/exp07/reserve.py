"""Reserve a synthetic stage record then leave it dispatching for crash sweep."""

import os
from laomedo.workflow_run_store import WorkflowRunStore


store = WorkflowRunStore("/state/runs.sqlite3")
record = store.reserve(graph={"nodes": [{"id": "Exp07ExternalStage"}]},
                       component_code={"Exp07ExternalStage": "EXP07_STAGE_V1"},
                       resolved_config={"grant": "disposable_canary_only"},
                       trigger={"type": "direct", "task": "orphan_test"})
print(record["run_id"], flush=True)
store.dispatch(record["run_id"], lambda _: os._exit(0))
