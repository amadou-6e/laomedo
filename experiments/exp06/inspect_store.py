"""Read a synthetic run record inside the disposable experiment container."""

import json
import sys

from laomedo.workflow_run_store import WorkflowRunStore


record = WorkflowRunStore("/state/runs.sqlite3").get(sys.argv[1])
print(json.dumps({key: record[key] for key in (
    "run_id", "trace_id", "status", "dispatch_attempts",
    "evidence_complete", "terminal_reason", "graph_revision",
    "resolved_config_ref")}, sort_keys=True))
