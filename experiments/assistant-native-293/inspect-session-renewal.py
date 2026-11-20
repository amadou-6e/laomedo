"""Read only owned assistant renewal counts; never read tokens or user content."""

import json
import os
from pathlib import Path
import sqlite3

database = Path(os.environ["LOCALAPPDATA"]) / "Laomedo/acceptance/assistant-saved-293-01a1ba85/langflow/flow.db"
with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
    conversation = os.environ["LAOMEDO_ACCEPTANCE_CONVERSATION"].replace("-", "")
    row = connection.execute(
        "SELECT state, session_key FROM laomedo_assistant_native_action "
        "WHERE conversation_id=? ORDER BY created_at DESC LIMIT 1", (conversation,)
    ).fetchone()
    aliases = connection.execute(
        "SELECT COUNT(*) FROM laomedo_assistant_session_alias WHERE canonical_key=?", (row[1],)
    ).fetchone()[0]
    authority = connection.execute(
        "SELECT revoked FROM laomedo_assistant_session WHERE key=?", (row[1],)
    ).fetchone()
    print(json.dumps({"latest_proposal_state": row[0], "verified_renewals_for_proposal": aliases,
                      "authority_revoked": bool(authority[0])}))
    for table in ("conversation", "message"):
        order = "" if table == "conversation" else " ORDER BY created_at DESC LIMIT 1"
        column = "id" if table == "conversation" else "conversation_id"
        state = connection.execute(
            "SELECT state, error_code, run_id FROM laomedo_assistant_" + table + " WHERE " + column + "=?" + order,
            (conversation,)
        ).fetchone()
        print(json.dumps({"record": table, "state": state[0], "error_code": state[1]}))
        if table == "conversation" and state[2]:
            # Exact owned run path is retained only in ignored local metadata.
            local = Path("C:/CodeWorkspace/laomedo/.tools/assistant-session-run-id.txt")
            local.write_text(state[2], encoding="utf-8")
