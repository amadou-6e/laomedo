"""Inspect schema/tool receipts from this task's exact synthetic acceptance message."""

import json
from pathlib import Path
import sqlite3
import sys

with sqlite3.connect(Path(sys.argv[1]).resolve().as_uri() + "?mode=ro", uri=True) as connection:
    for (encoded,) in connection.execute(
        "SELECT activity_snapshot FROM laomedo_assistant_message WHERE text LIKE ?",
        ("Use ONLY Laomedo MCP tools for this bounded acceptance check.%",),
    ):
        snapshot = json.loads(encoded)
        print(json.dumps({"snapshot_keys": list(snapshot)}))
        for key, value in snapshot.items():
            if isinstance(value, list):
                print(json.dumps({"list": key, "items": len(value), "first_item_keys": list(value[0]) if value and isinstance(value[0], dict) else []}))
        calls = {}
        for record in snapshot.get("records", []):
            event = record["event"]
            if event.get("kind") == "tool_call":
                calls[event["tool_call_id"]] = event.get("name", "")
                print(json.dumps({"name": event.get("name"), "arguments": event.get("arguments")}))
            if event.get("kind") == "tool_result":
                print(json.dumps({"name": calls.get(event["tool_call_id"]), "output": str(event.get("output"))[:4500]}))
