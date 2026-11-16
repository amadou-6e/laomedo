"""Real per-turn selection acceptance, isolated from the owner's presentation chat."""

import json
from pathlib import Path
import time
import urllib.request
from uuid import uuid4

workspace = Path("C:/CodeWorkspace/laomedo")
metadata = json.loads((workspace / ".tools/assistant-282-live.json").read_text())
state = Path(metadata["state"])
base = metadata["base"]
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
token = json.load(opener.open(base + "/api/v1/auto_login", timeout=30))["access_token"]
headers = {
    "Authorization": "Bearer " + token,
    "Origin": base,
    "Content-Type": "application/json",
}


def request(path, body=None):
    """Issue one exact local request; no prompt retries or credential logging."""
    req = urllib.request.Request(
        base + "/api/v1/laomedo/assistant" + path,
        data=None if body is None else json.dumps(body).encode(),
        headers=headers,
    )
    return json.load(opener.open(req, timeout=180))


catalog = request("/models")
choices = {item["id"]: item["efforts"] for item in catalog["models"]}
assert "medium" in choices["gpt-6-luna"] and "low" in choices["gpt-5.6-luna"]
conversation = request(
    "/conversations", {"provider": "codex", "model": "gpt-6-luna", "effort": "low"}
)["id"]
observations = []
for model, effort, prompt in (
    (
        "gpt-6-luna",
        "low",
        "Remember the marker cobalt. Reply only cobalt. Do not use tools.",
    ),
    (
        "gpt-6-luna",
        "medium",
        "What marker did I ask you to remember? Reply only the marker. Do not use tools.",
    ),
    (
        "gpt-5.6-luna",
        "low",
        "What marker did I ask you to remember? Reply only the marker. Do not use tools.",
    ),
):
    message = request(
        f"/conversations/{conversation}/messages",
        {
            "client_message_id": str(uuid4()),
            "text": prompt,
            "model": model,
            "effort": effort,
        },
    )
    for _ in range(150):
        detail = request(f"/conversations/{conversation}")
        row = next(item for item in detail["messages"] if item["id"] == message["id"])
        if detail["conversation"]["active_message_id"] is None:
            break
        time.sleep(2)
    assert row["state"] == "completed", (row["state"], row["error_code"])
    assert "cobalt" in row["response"].lower()
    assert (row["model"], row["effort"]) == (model, effort)
    binding = detail["conversation"]
    paths = list(
        (state / "assistant").glob(f"*/*/runner/runs/{binding['run_id']}/record.json")
    )
    assert len(paths) == 1
    record = json.loads(paths[0].read_text(encoding="utf-8"))
    assert (record["effective_model"], record["effective_effort"]) == (model, effort)
    observations.append(
        {
            "model": model,
            "effort": effort,
            "thread": binding["thread_id"],
            "run": binding["run_id"],
            "completed": True,
            "marker_recalled": True,
        }
    )
    print(json.dumps(observations[-1]), flush=True)
assert len({row["thread"] for row in observations}) == 1
assert len({row["run"] for row in observations}) == 1
summary = {
    "conversation": conversation,
    "turns": observations,
    "same_native_thread": True,
    "same_run": True,
}
(state / "selection-acceptance.json").write_text(json.dumps(summary), encoding="utf-8")
print(
    json.dumps(
        {
            "same_native_thread": True,
            "same_run": True,
            "turns_completed": len(observations),
        }
    ),
    flush=True,
)
