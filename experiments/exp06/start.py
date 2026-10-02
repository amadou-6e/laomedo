"""Startup sweep before launching the fate-shared synthetic Langflow backend."""

import os
import sys

sys.path.insert(0, "/laomedo-src")
from laomedo.workflow_run_store import WorkflowRunStore


store = WorkflowRunStore("/state/runs.sqlite3")
print("exp06_startup_swept=" + str(len(store.sweep_crashed())), flush=True)
os.execvp("langflow", ["langflow", "run"])
