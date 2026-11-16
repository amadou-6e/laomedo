"""Read-only final evidence from the isolated app; emit no login or capability data."""
import json
from pathlib import Path
import sqlite3
import sys
from uuid import UUID

root = Path("C:/CodeWorkspace/laomedo")
sys.path.insert(0, str(root / ".tools/worktrees/assistant-282/src"))
from sqlalchemy import text
from sqlmodel import Session, create_engine, select
from langflow.services.database.models.flow.model import Flow
from laomedo.integrations.langflow.assistant.workflows import WorkflowDrafts

m = json.loads((root / ".tools/assistant-282-live.json").read_text())
state = Path(m["state"])
before = json.loads((state / "restart-before.json").read_text())
after = json.loads((state / "acceptance-detail.json").read_text())
db = state / "app/flow.db"
connection = sqlite3.connect(db)
connection.execute("PRAGMA query_only=ON")
source_id, source_revision = connection.execute("select workflow_id, revision from laomedo_assistant_draft_receipt where conversation_id=?", (m["previous_conversation"].replace("-", ""),)).fetchone()
prior_states = [row[0] for row in connection.execute("select state from laomedo_assistant_message where conversation_id=? order by created_at", (m["previous_conversation"].replace("-", ""),))]
stop_observations = [json.loads(line) for line in (root / ".tools/assistant-282-stop.log").read_text(encoding="utf-16").splitlines() if line.startswith("{")]
engine = create_engine("sqlite:///" + db.as_posix())
with Session(engine) as session:
    session.execute(text("PRAGMA query_only=ON"))
    source = session.exec(select(Flow).where(Flow.id == UUID(source_id))).one()
    observed_source_revision = WorkflowDrafts(None, None, None).revision(source)
engine.dispose()
connection.close()
record_paths = list((state / "assistant").glob("*/*/runner/runs/" + after["conversation"]["run_id"] + "/record.json"))
record = json.loads(record_paths[0].read_text())
result = {
    "fresh_real_mcp_save": bool(source_id and len(record.get("mcp_manifest", {}).get("tools", [])) == 6),
    "ordinary_follow_up_completed": prior_states[:2] == ["completed", "completed"],
    "active_stop_settled_cancelled_same_thread": stop_observations[-1]["state"] == "cancelled" and stop_observations[-1]["same_thread"],
    "post_stop_follow_up_completed": "cancelled" in prior_states and prior_states[prior_states.index("cancelled") + 1] == "completed",
    "restart_follow_up_completed": after["messages"][-1]["state"] == "completed",
    "restart_kept_same_native_thread": before["conversation"]["thread_id"] == after["conversation"]["thread_id"],
    "restart_kept_same_run": before["conversation"]["run_id"] == after["conversation"]["run_id"],
    "restart_kept_identical_receipts": before["drafts"] == after["drafts"],
    "source_workflow_unchanged": observed_source_revision == source_revision,
    "copy_receipts": len(after["drafts"]),
    "native_controller_cleanup": record["controller_cleanup"],
    "native_resource_cleanup_verified": record["container_ownership"]["cleanup_verified"],
    "image_id": record["image_id"],
    "browser": json.loads((root / ".tools/assistant-282-browser.log").read_text(encoding="utf-16").strip()),
}
print(json.dumps(result, indent=2))
