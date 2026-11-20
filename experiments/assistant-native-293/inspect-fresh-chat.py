"""Read the known acceptance marker only; do not dump user chat or credentials."""

import json
import os
from pathlib import Path
import sqlite3

database = Path(os.environ["LOCALAPPDATA"]) / "Laomedo/acceptance/assistant-saved-293-01a1ba85/langflow/flow.db"
with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
    row = connection.execute(
        "SELECT conversation_id, state, error_code, response FROM laomedo_assistant_message "
        "WHERE text=? ORDER BY created_at DESC LIMIT 1",
        ("Reply exactly ACCOUNT-FINAL-SEND-293. Do not use tools.",)
    ).fetchone()
    Path("C:/CodeWorkspace/laomedo/.tools/assistant-fresh-chat-id.txt").write_text(row[0], encoding="utf-8")
    print(json.dumps({"state": row[1], "error_code": row[2], "marker_matches": row[3] == "ACCOUNT-FINAL-SEND-293"}))
