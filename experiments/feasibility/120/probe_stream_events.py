"""Probe raw streamed tool-call and result events from Codex app-server.

REQUIRES A DEDICATED CREDENTIAL. Do not run without one.
The probe checks auth first and stops before any model call if no credential
is available. Submits a turn that triggers a tool call, then captures every
event the app-server emits.

Credential gate:
- --state-dir must contain codex-home/auth.json with a file-backed ChatGPT auth.
- If auth is missing or login status fails, the probe stops.
- No credential is logged or committed.
"""

import argparse
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shared import (construct_env, hash_personal_roots, initialize,
                      list_skills, list_models, personal_roots, read_lines,
                      request, start_turn, stop_app_server, write_skill)


MARKER = "LAOMEDO_120_STREAM"
SKILL_NAME = "fixture-stream-120"
SKILL_CONTENT = (
    "---\nname: fixture-stream-120\n"
    "description: Synthetic tool-call fixture. Replies with a file listing.\n"
    "---\n\n"
    "# Stream Probe\n\n"
    "When invoked, list the files in the current working directory using a "
    "bash tool call, then reply with the exact marker: "
    f"{MARKER}. Make exactly one tool call.\n"
)


def check_auth(codex, state_dir, env):
    result = subprocess.run(
        [str(codex), "login", "status"],
        cwd=state_dir, env=env,
        capture_output=True, text=True, timeout=20, encoding="utf-8",
        errors="replace",
    )
    output = (result.stdout + result.stderr).lower()
    return {
        "exit_code": result.returncode,
        "chatgpt_login": result.returncode == 0 and "chatgpt" in output,
        "api_key": "api key" in output,
    }


def check_connectivity():
    try:
        with socket.create_connection(("chatgpt.com", 443), timeout=3):
            return True
    except OSError:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True,
                        help="private runner state dir with codex-home/auth.json")
    parser.add_argument("--run", action="store_true", help="start one model turn")
    args = parser.parse_args()
    codex = args.codex.resolve(strict=True)
    state = args.state_dir.resolve(strict=True)
    private_home = state / "home"; codex_home = state / "codex-home"
    project = state / "project"
    project.mkdir(parents=True, exist_ok=True)

    write_skill(project / ".agents" / "skills", SKILL_NAME, SKILL_CONTENT)

    env = construct_env(private_home, codex_home, state, codex.parent)
    before = hash_personal_roots()
    summary = {"model_calls": 0}

    # Credential gate
    if not (codex_home / "auth.json").is_file():
        summary["credential_gate"] = "missing_auth_file"
        return print(json.dumps(summary, indent=2))

    auth = check_auth(codex, state, env)
    summary["auth_check"] = auth
    if not auth["chatgpt_login"]:
        summary["credential_gate"] = "no_chatgpt_login"
        return print(json.dumps(summary, indent=2))

    reachable = check_connectivity()
    summary["chatgpt_reachable"] = reachable
    if not reachable:
        summary["credential_gate"] = "no_connectivity"
        return print(json.dumps(summary, indent=2))

    process, messages, error_log = None, None, None
    try:
        error_log = (state / "app-server.stderr.log").open("w", encoding="utf-8")
        process = subprocess.Popen(
            [str(codex), "app-server", "--stdio"], cwd=project, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=error_log,
            text=True, encoding="utf-8",
        )
        messages = queue.Queue()
        import threading
        threading.Thread(target=read_lines, args=(process.stdout, messages), daemon=True).start()
        pending = []

        ok, init_resp = initialize(process, messages)
        summary["initialized"] = ok
        if not ok:
            summary["init_error"] = init_resp.get("error", {}).get("code")
            return print(json.dumps(summary, indent=2))
        process.stdin.write(json.dumps({"method": "initialized", "params": {}}) + "\n")
        process.stdin.flush()

        skills = list_skills(process, messages, project)
        names = {s.get("name") for s in skills}
        summary["fixture_discovered"] = SKILL_NAME in names

        _mr, models = list_models(process, messages)
        default = next((m for m in models if m.get("isDefault")), None)
        if not default and models:
            default = models[0]
        model = default.get("id") or default.get("model")
        summary["selected_model"] = model

        if not args.run:
            return print(json.dumps(summary, indent=2))

        if not summary["fixture_discovered"]:
            summary["blocked_before_turn"] = "fixture_not_discovered"
            return print(json.dumps(summary, indent=2))

        # Start thread + turn with skill
        thr = request(process, messages, {
            "method": "thread/start", "id": 4,
            "params": {"model": model, "cwd": str(project),
                       "approvalPolicy": "never",
                       "config": {"model_reasoning_effort": "low"},
                       "sandbox": "read-write"},
        }, timeout=30)
        if "error" in thr:
            summary["thread_error"] = thr["error"].get("code")
        else:
            thread_id = thr["result"].get("thread", {}).get("id")
            summary["thread_id"] = thread_id
            summary["model_calls"] = 1

            turn = request(process, messages, {
                "method": "turn/start", "id": 5,
                "params": {"threadId": thread_id, "input": [
                    {"type": "skill", "name": SKILL_NAME,
                     "path": str(project / ".agents" / "skills" / SKILL_NAME / "SKILL.md")},
                ]},
            }, timeout=30)
            summary["turn_accepted"] = "result" in turn

            # Collect ALL events until turn/completed or timeout
            events = []
            methods = {}
            output = []
            tool_calls = []
            tool_results = []
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                try:
                    item = pending.pop(0) if pending else messages.get(timeout=1)
                except queue.Empty:
                    continue
                method = item.get("method", "")
                methods[method] = methods.get(method, 0) + 1
                params = item.get("params", {})

                if method in ("item/started", "item/updated", "item/completed"):
                    it = params.get("item", {})
                    itype = it.get("type")
                    if itype == "agentMessage":
                        output.append(it.get("text", ""))
                    elif itype == "toolCall":
                        tool_calls.append({
                            "id": it.get("id"), "name": it.get("name"),
                            "arguments": it.get("arguments"),
                            "status": it.get("status"),
                        })
                    elif itype == "toolResult":
                        tool_results.append({
                            "id": it.get("id"),
                            "output": it.get("output"),
                            "error": it.get("error"),
                        })
                    events.append({"method": method, "type": itype,
                                   "id": it.get("id"), "status": it.get("status")})

                if method == "turn/completed":
                    summary["turn_status"] = params.get("turn", {}).get("status")
                    break

            summary["event_count"] = len(events)
            summary["output_texts"] = len(output)
            summary["marker_returned"] = any(MARKER in t for t in output)
            summary["tool_calls_observed"] = len(tool_calls)
            summary["tool_results_observed"] = len(tool_results)
            summary["tool_call_names"] = [tc["name"] for tc in tool_calls]
            summary["event_methods"] = {k: v for k, v in methods.items() if k in
                ("item/started", "item/updated", "item/completed",
                 "turn/completed", "thread/tokenUsage/updated")}
            summary["redacted_events"] = events

        print(json.dumps(summary, indent=2))
    finally:
        if process:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if error_log:
            error_log.close()
        error_text = (state / "app-server.stderr.log").read_text(encoding="utf-8", errors="replace").lower()
        print(json.dumps({"stderr_signals": {
            "authentication": any(x in error_text for x in ("auth", "unauthorized", "token expired")),
            "network": any(x in error_text for x in ("connection", "network", "dns", "timeout")),
            "sandbox": "sandbox" in error_text,
            "nonempty": bool(error_text.strip()),
        }}, indent=2))
        after = hash_personal_roots()
        print(json.dumps({"personal_roots_unchanged": dict(
            ("_".join(r.parts[-2:]) if len(r.parts) > 1 else r.name,
             a == b) for r, a, b in zip(personal_roots(), before, after))}, indent=2))


if __name__ == "__main__":
    main()
