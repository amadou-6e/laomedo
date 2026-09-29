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
from _shared import (AppServer, RequestTimeout, codex_version,
                      compare_personal_roots, construct_env, credential_gate,
                      fingerprint, hash_personal_roots, read_turn_context,
                      reserve_model_turn, select_supported_pair,
                      summarize_methods, validate_pair,
                      write_skill)

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

CALL_ITEM_TYPES = {
    "commandExecution": {"call": ("command",),
                         "result": ("aggregatedOutput", "exitCode")},
    "mcpToolCall": {"call": ("server", "tool", "arguments"),
                    "result": ("result", "error")},
    "dynamicToolCall": {"call": ("tool", "arguments"),
                        "result": ("contentItems", "success")},
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


def stream_evidence(events):
    """Only a terminal completed item can establish the result of a call."""
    started = {}
    completed = {}
    for message in events:
        method = message.get("method")
        if method not in ("item/started", "item/completed"):
            continue
        params = message.get("params", {})
        item = params.get("item", {})
        key = (params.get("threadId"), params.get("turnId"),
               item.get("type"), item.get("id"))
        if method == "item/started":
            started[key] = item
        else:
            completed[key] = item
    matched = []
    for key, final_item in completed.items():
        initial = started.get(key)
        spec = CALL_ITEM_TYPES.get(final_item.get("type"))
        if not initial or not spec:
            continue
        if not any(field in initial for field in spec["call"]):
            continue
        if final_item.get("status") not in ("completed", "failed"):
            continue
        kind = final_item["type"]
        if kind == "commandExecution":
            result_present = (isinstance(final_item.get("exitCode"), int)
                              or isinstance(final_item.get("aggregatedOutput"), str))
        elif kind == "mcpToolCall":
            result_present = (final_item.get("result") is not None
                              or final_item.get("error") is not None)
        else:
            result_present = (isinstance(final_item.get("success"), bool)
                              or final_item.get("contentItems") is not None)
        if not result_present:
            continue
        matched.append(redact_item(final_item))
    return {
        "started_item_count": len(started),
        "completed_item_count": len(completed),
        "incomplete_item_count": len(started.keys() - completed.keys()),
        "completed_items": [redact_item(item) for item in completed.values()],
        "matching_tool_results": matched,
        "tool_call_and_result_observed": bool(matched),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path,
                        help="provisioned private state dir with codex-home/auth.json")
    parser.add_argument("--credential-mode", choices=("chatgpt_handoff", "api_key"),
                        default="chatgpt_handoff")
    parser.add_argument("--credential-ref", help="API-key secret-store reference, not a key")
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
    gate = credential_gate(codex, project, env, codex_home, state,
                           args.credential_mode, args.credential_ref)
    summary["credential_gate"] = gate
    if not gate.get("permitted"):
        print(json.dumps(summary, indent=2))
        return

    before = hash_personal_roots()
    source_workspace_hash = fingerprint(project)
    server = AppServer(codex, project, env, state)
    summary["private_event_log"] = server.event_log_path.name
    try:
        ok, info = server.initialize()
        summary["initialized"] = ok
        summary["server_platform"] = {k: info.get(k) for k in ("userAgent", "platformFamily", "platformOs")}
        if not ok:
            return

        skills = server.send("skills/list", {"cwds": [str(project)], "forceReload": True})
        names = {s.get("name") for s in skills.get("result", {}).get("data", [{}])[0].get("skills", [])}
        summary["fixture_discovered"] = SKILL_NAME in names

        models = server.send("model/list", {"limit": 100})
        model, effort, capabilities = select_supported_pair(
            models, preferred_model="gpt-6-luna")
        summary["requested_settings"] = {"model": model, "effort": effort}
        summary["pair_validation"] = validate_pair(capabilities, model, effort)

        if not args.run:
            summary["preflight_only"] = True
            return
        if not summary["fixture_discovered"]:
            summary["blocked_before_turn"] = "fixture_not_discovered"
            return

        started = server.send("thread/start", {
            "model": model, "cwd": str(project), "approvalPolicy": "never",
            "sandbox": "read-only",
        }, timeout=30)
        if "error" in started:
            summary["thread_error"] = started["error"]
            return
        thread_id = started["result"]["thread"]["id"]
        thread_path = started["result"]["thread"].get("path")
        summary["thread_id"] = thread_id
        summary["cli_version"] = started["result"]["thread"].get("cliVersion")

        # One invocation channel only: the explicit skill input item. The
        # "$<name>" text mention from #119 is deliberately omitted so a
        # positive result is attributable to the skill item alone.
        # Counted before sending: an attempted turn/start is an upper bound on
        # billable model calls even if this request itself times out.
        summary["cumulative_attempted_turns"] = reserve_model_turn(state)
        summary["model_calls"] = summary.get("model_calls", 0) + 1
        turn = server.send("turn/start", {
            "threadId": thread_id,
            "input": [
                {"type": "text", "text": "Follow the skill."},
                {"type": "skill", "name": SKILL_NAME,
                 "path": str(project / ".agents" / "skills" / SKILL_NAME / "SKILL.md")},
            ],
            "model": model, "effort": effort,
        }, timeout=30)
        if "error" in turn:
            summary["turn_start_error"] = turn["error"]
            return
        turn_id = turn.get("result", {}).get("turn", {}).get("id")
        summary["turn_id"] = turn_id

        # Wait for terminal turn status, then a short settle drain. On timeout,
        # keep whatever events arrived; the finally block still prints them.
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
        summary["effective_context"] = read_turn_context(
            codex_home, thread_path, turn_id)
        summary["turn_diff_seen"] = any(m.get("method") == "turn/diff/updated" for m in server.events)
    except RequestTimeout as exc:
        # A timeout after turn/start still leaves the events collected so far;
        # keep them and report the timeout rather than losing the paid turn.
        summary["fatal_timeout"] = str(exc)
    except Exception as exc:
        summary["fatal"] = type(exc).__name__
    finally:
        summary.update(stream_evidence(server.events))
        summary["event_methods"] = summarize_methods(server)
        summary["usage_event_count"] = summary["event_methods"].get(
            "thread/tokenUsage/updated", 0)
        summary["read_only_workspace_unchanged"] = (
            fingerprint(project) == source_workspace_hash)
        stderr = server.close()
        summary["stderr_signals"] = stderr
        summary["model_calls_note"] = ("upper bound on billable model calls: a "
                                       "turn/start is counted when submitted, "
                                       "before any response")
        print(json.dumps(summary, indent=2))
        print(json.dumps({"personal_roots_unchanged":
                          compare_personal_roots(before, hash_personal_roots())}, indent=2))


if __name__ == "__main__":
    main()
