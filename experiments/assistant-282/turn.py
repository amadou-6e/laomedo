"""Submit one explicitly selected live acceptance prompt and observe, never retry it."""

import json
from pathlib import Path
import sys
import time
import urllib.request
from uuid import uuid4

workspace = Path("C:/CodeWorkspace/laomedo")
metadata = json.loads((workspace / ".tools/assistant-282-live.json").read_text())
state = Path(metadata["state"])
token = json.loads((state / "acceptance-session.json").read_text())["token"]
base = metadata["base"]
headers = {
    "Authorization": "Bearer " + token,
    "Origin": base,
    "Content-Type": "application/json",
}


def request(path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        base + "/api/v1/laomedo/assistant" + path, data=data, headers=headers
    )
    try:
        return json.load(urllib.request.urlopen(req, timeout=180))
    except urllib.error.HTTPError as error:
        print(
            json.dumps(
                {"stage": "refused", "status": error.code, "result": json.load(error)}
            ),
            flush=True,
        )
        raise SystemExit(1)


if len(sys.argv) > 1 and sys.argv[1] == "--linked":
    previous = metadata["conversation"]
    conversation = request(
        "/conversations",
        {
            "provider": "codex",
            "model": "gpt-6-luna",
            "effort": "low",
            "linked_conversation_id": previous,
        },
    )["id"]
    metadata.update(conversation=conversation, previous_conversation=previous)
    (workspace / ".tools/assistant-282-live.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
elif len(sys.argv) > 1:
    conversation = sys.argv[1]
else:
    conversation = request(
        "/conversations", {"provider": "codex", "model": "gpt-6-luna", "effort": "low"}
    )["id"]
    metadata["conversation"] = conversation
    (workspace / ".tools/assistant-282-live.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
prompt = "Use the Laomedo MCP tools to discover and describe the installed Chat Input and Chat Output components. Save a separate workflow named Assistant presentation draft connecting them using the exact discovered ports. You may save an explicitly incomplete structural draft if installed settings cannot be copied, and explain why. Do not run or publish it."
if len(sys.argv) > 2:
    prompt = sys.argv[2]
message = request(
    f"/conversations/{conversation}/messages",
    {"client_message_id": str(uuid4()), "text": prompt},
)
print(
    json.dumps(
        {"stage": "submitted", "conversation": conversation, "message": message["id"]}
    ),
    flush=True,
)
for _ in range(180):
    detail = request(f"/conversations/{conversation}")
    row = next(row for row in detail["messages"] if row["id"] == message["id"])
    print(
        json.dumps(
            {
                "stage": "observation",
                "state": row["state"],
                "error": row["error_code"],
                "receipts": len(detail["drafts"]),
            }
        ),
        flush=True,
    )
    if detail["conversation"]["active_message_id"] is None:
        (state / "acceptance-detail.json").write_text(
            json.dumps(detail), encoding="utf-8"
        )
        break
    time.sleep(2)
