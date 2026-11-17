"""Read-only proof of compact-approval acceptance against isolated runtime state."""

import json
from pathlib import Path
import sqlite3


metadata = json.loads(Path(r"C:/CodeWorkspace/laomedo/.tools/assistant-291-live.json").read_text())
database = Path(metadata["state"]) / "app/flow.db"
with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
    rows = connection.execute(
        "SELECT operation_key, state, name, request, run_id, conversation_id, owner_id FROM laomedo_assistant_graph_action WHERE operation_key LIKE 'compact-%' ORDER BY created_at"
    ).fetchall()
    actions = []
    for key, state, name, raw, run_id, conversation, owner in rows:
        request = json.loads(raw)
        target = connection.execute("SELECT name FROM flow WHERE id = ?", (request["workflow_id"].replace("-", ""),)).fetchone()
        job = connection.execute("SELECT status, user_id, flow_id FROM job WHERE job_id = ?", (run_id,)).fetchone() if run_id else None
        job_proof = {"completed": bool(job and job[0] == "completed"), "exactOwnerFlow": bool(job and job[1] == owner and job[2] == request["workflow_id"].replace("-", ""))} if run_id else None
        actions.append({"key": key, "state": state, "targetName": target[0] if target else None, "runId": run_id, "job": job_proof})
    grants = connection.execute("SELECT category, count(*) FROM laomedo_assistant_graph_permission GROUP BY category").fetchall()
print(json.dumps({"actions": actions, "grants": dict(grants)}))
