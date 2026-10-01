"""Extract only native linkage IDs from a private synthetic Codex rollout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


ITEM_ID = re.compile(r"^(?:ctc_|ctco_)[A-Za-z0-9_-]{12,100}$")
CALL_ID = re.compile(r"^call_[A-Za-z0-9_-]{12,100}$")
SESSION_ID = re.compile(r"^[0-9a-f-]{36}$")


def sample(text: str, max_pairs: int = 2) -> dict:
    calls: dict[str, dict] = {}
    results: dict[str, dict] = {}
    session_id = None
    for line in text.splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        payload = record.get("payload", {})
        if not isinstance(payload, dict):
            continue
        if record.get("type") == "session_meta" and isinstance(payload.get("id"), str) and SESSION_ID.fullmatch(payload["id"]):
            session_id = payload["id"]
        if record.get("type") != "response_item":
            continue
        item_type = payload.get("type")
        call_id = payload.get("call_id")
        item_id = payload.get("id")
        if item_type not in {"custom_tool_call", "custom_tool_call_output"}:
            continue
        if not isinstance(call_id, str) or not CALL_ID.fullmatch(call_id):
            continue
        if not isinstance(item_id, str) or not ITEM_ID.fullmatch(item_id):
            continue
        entry = {"item_type": item_type, "item_id": item_id, "call_id": call_id}
        (calls if item_type == "custom_tool_call" else results)[call_id] = entry
    pairs = [{"call": calls[key], "result": results[key]} for key in calls if key in results][:max_pairs]
    return {
        "source": "codex_rollout_response_item",
        "redaction": "whitelist_only_ids_and_types_no_content",
        "native_session_id": session_id,
        "pairs": pairs,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rollout", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = sample(args.rollout.read_text(encoding="utf-8"))
    if not result["pairs"]:
        raise SystemExit("no matching custom tool call/result pairs")
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
