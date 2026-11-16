"""One bounded active-turn cancellation check; no retries and no workflow effects."""

import json
from pathlib import Path
import time
import urllib.request
from uuid import uuid4

root = Path("C:/CodeWorkspace/laomedo")
m = json.loads((root / ".tools/assistant-282-live.json").read_text())
state = Path(m["state"])
token = json.loads((state / "acceptance-session.json").read_text())["token"]
headers = {
    "Authorization": "Bearer " + token,
    "Origin": m["base"],
    "Content-Type": "application/json",
}
prefix = m["base"] + "/api/v1/laomedo/assistant/conversations/" + m["conversation"]


def call(path="", body=None):
    request = urllib.request.Request(
        prefix + path,
        headers=headers,
        data=None if body is None else json.dumps(body).encode(),
    )
    return json.load(urllib.request.urlopen(request, timeout=40))


message = call(
    "/messages",
    {
        "client_message_id": str(uuid4()),
        "text": "Use the Laomedo MCP to inspect the existing saved workflow and the installed component descriptions. Then explain in detail ten different ways a chat workflow could be extended, with trade-offs for each. Do not save, execute, publish or delete anything.",
    },
)
active_thread = None
for _ in range(40):
    detail = call()
    if detail["conversation"]["active_message_id"] is None:
        raise RuntimeError("turn_finished_before_cancellation")
    activity = call("/activity?attempt=" + message["attempt_id"] + "&after=0")
    if activity.get("thread_id") and activity.get("projection", {}).get("items"):
        active_thread = activity["thread_id"]
        break
    time.sleep(0.5)
if not active_thread:
    raise RuntimeError("active_native_session_not_observed")
print(
    json.dumps({"stage": "stop_requested", "native_session_observed": True}), flush=True
)
call("/stop", {"attempt_id": message["attempt_id"]})
for _ in range(90):
    detail = call()
    row = next(row for row in detail["messages"] if row["id"] == message["id"])
    if detail["conversation"]["active_message_id"] is None:
        print(
            json.dumps(
                {
                    "stage": "settled",
                    "state": row["state"],
                    "conversation_state": detail["conversation"]["state"],
                    "same_thread": detail["conversation"]["thread_id"] == active_thread,
                    "receipts": len(detail["drafts"]),
                }
            ),
            flush=True,
        )
        (state / "acceptance-stop.json").write_text(
            json.dumps(detail), encoding="utf-8"
        )
        break
    time.sleep(1)
else:
    raise RuntimeError("cancellation_settlement_not_observed")
