"""Probe raw streamed tool-call and result events from Codex app-server.

Credential required. The credential gate accepts a dedicated API-key credential
and stops before any model call otherwise.

Submits a turn whose skill asks for one command execution, then records every
item notification. Item types follow the app-server reference: commandExecution,
fileChange, mcpToolCall, dynamicToolCall, webSearch, and so on. Each item
carries its own call and result fields; there is no separate toolCall/toolResult
item type.
"""

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shared import (AppServer, codex_version, compare_personal_roots,
                      construct_env, credential_gate, hash_personal_roots,
                      summarize_methods, write_skill)

MARKER = "LAOMEDO_120_STREAM"
SKILL_NAME = "fixture-stream-120"
SKILL_CONTENT = (
    "---\nname: fixture-stream-120\n"
    "description: Synthetic tool-call fixture.\n"
    "---\n\n"
    "# Stream Probe\n\n"
    "Run exactly one shell command that lists the files in the current working "
    "directory. After the command finishes, reply with the exact marker "
    f"{MARKER}.\n"
)

# Per the app-server reference, these item types can carry a tool call and a
# result in the same item.
CALL_ITEM_TYPES = {
    "commandExecution": {"call": ["command", "cwd"], "result": ["aggregatedOutput", "exitCode", "status"]},
    "fileChange": {"call": ["changes"], "result": ["status"]},
    "mcpToolCall": {"call": ["server", "tool", "arguments"], "result": ["result", "error", "status"]},
    "dynamicToolCall": {"call": ["tool", "arguments"], "result": ["contentItems", "success", "status"]},
    "webSearch": {"call": ["query"], "result": ["action"]},
    "imageView": {"call": ["path"], "result": []},
}


def redact_item(item):
    itype = item.get("type")
    fields = sorted(item.keys())
    spec = CALL_ITEM_TYPES.get(itype, {})
    has_call = any(f in item for f in spec.get("call", [])) if spec else False
    has_result = any(f in item for f in spec.get("result", [])) if spec else False
    return {
        "type": itype,
        "id": item.get("id"),
        "status": item.get("status"),
        "fields": fields,
        "has_call_field": has_call,
        "has_result_field": has_result,
        "exit_code": item.get("exitCode"),
        "output_present": bool(item.get("aggregatedOutput") or item.get("result")
                               or item.get("contentItems")),
        "error_present": bool(item.get("error")),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path,
                        help="provisioned private state dir with codex-home/auth.json")
    parser.add_argument("--run", action="store_true", help="submit the model turn")
    args = parser.parse_args()
    codex = args.codex.resolve(strict=True)
    if not args.state_dir:
        print(json.dumps({"blocked": "no_state_dir"}, indent=2))
        return
    state = args.state_dir.resolve(strict=True)
    private_home = state / "home"
    codex_home = state / "codex-home"
    project = state / "project"
    for directory in (private_home, codex_home, project):
        directory.mkdir(parents=True, exist_ok=True)
    write_skill(project / ".agents" / "skills", SKILL_NAME, SKILL_CONTENT)
    env = construct_env(private_home, codex_home, state, codex.parent)

    summary = {"version": codex_version(codex, env), "model_calls": 0}
    gate = credential_gate(codex, project, env, codex_home, state)
    summary["credential_gate"] = gate
    if not gate.get("permitted"):
        print(json.dumps(summary, indent=2))
        return

    before = hash_personal_roots()
    server = AppServer(codex, project, env, state)
    try:
        ok, info = server.initialize()
        summary["initialized"] = ok
        summary["server_platform"] = {k: info.get(k) for k in ("userAgent", "platformFamily", "platformOs")}
        if not ok:
            print(json.dumps(summary, indent=2))
            return

        skills = server.send("skills/list", {"cwds": [str(project)], "forceReload": True})
        names = {s.get("name") for s in skills.get("result", {}).get("data", [{}])[0].get("skills", [])}
        summary["fixture_discovered"] = SKILL_NAME in names

        models = server.send("model/list", {"limit": 100})
        data = models.get("result", {}).get("data", [])
        selected = next((m for m in data if m.get("isDefault")), None) or (data[0] if data else None)
        model = (selected or {}).get("id") or (selected or {}).get("model")
        summary["selected_model"] = model

        if not args.run:
            summary["preflight_only"] = True
            print(json.dumps(summary, indent=2))
            return
        if not summary["fixture_discovered"]:
            summary["blocked_before_turn"] = "fixture_not_discovered"
            print(json.dumps(summary, indent=2))
            return

        started = server.send("thread/start", {
            "model": model, "cwd": str(project), "approvalPolicy": "never",
            "sandbox": "read-only",
        }, timeout=30)
        if "error" in started:
            summary["thread_error"] = started["error"]
            print(json.dumps(summary, indent=2))
            return
        thread_id = started["result"]["thread"]["id"]
        summary["thread_id"] = thread_id

        turn = server.send("turn/start", {
            "threadId": thread_id,
            "input": [
                {"type": "text", "text": f"${SKILL_NAME} Follow the skill."},
                {"type": "skill", "name": SKILL_NAME,
                 "path": str(project / ".agents" / "skills" / SKILL_NAME / "SKILL.md")},
            ],
            "model": model, "effort": "low",
        }, timeout=30)
        if "error" in turn:
            summary["turn_start_error"] = turn["error"]
            print(json.dumps(summary, indent=2))
            return
        summary["model_calls"] = 1

        # Wait for terminal turn status, then a short settle drain.
        deadline = time.monotonic() + 120
        status = None
        while time.monotonic() < deadline:
            for message in server.events:
                if message.get("method") == "turn/completed":
                    status = message.get("params", {}).get("turn", {}).get("status")
            if status is not None:
                break
            server.drain(0.5)
        server.drain(1.0)
        summary["turn_status"] = status or "timeout"

        items = {}
        for message in server.events:
            if message.get("method") in ("item/started", "item/completed"):
                item = message.get("params", {}).get("item", {})
                key = (item.get("type"), item.get("id"))
                items[key] = item
        redacted = [redact_item(item) for item in items.values()]
        calls = [r for r in redacted if r["type"] in CALL_ITEM_TYPES and r["has_call_field"]]
        with_result = [r for r in calls if r["has_result_field"] or r["output_present"] or r["error_present"]]
        summary["items"] = redacted
        summary["call_item_count"] = len(calls)
        summary["call_with_result_count"] = len(with_result)
        summary["tool_call_and_result_observed"] = bool(with_result)
        summary["turn_diff_seen"] = any(m.get("method") == "turn/diff/updated" for m in server.events)
        summary["event_methods"] = summarize_methods(server)
        print(json.dumps(summary, indent=2))
    finally:
        stderr = server.close()
        print(json.dumps({"stderr_signals": stderr}, indent=2))
        print(json.dumps({"personal_roots_unchanged":
                          compare_personal_roots(before, hash_personal_roots())}, indent=2))


if __name__ == "__main__":
    main()
