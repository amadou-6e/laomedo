"""Run one synthetic native-skill turn in a private Codex profile.

Only sanitized observations reach stdout. The private auth and raw session stay
under --state-dir, which must be outside the repository.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import threading
import time

from probe_codex_discovery import fingerprint, read_lines
from check_private_auth import require_outside_git_worktree


MARKER = "LAOMEDO_NATIVE_SKILL_119"
SKILL_NAME = "fixture-native-119"


class RequestTimeout(TimeoutError):
    def __init__(self, method):
        super().__init__(f"app-server response timed out for {method}")
        self.method = method


def hash_path(path):
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    return fingerprint(path)


def request(process, messages, payload, pending=None, timeout=20):
    process.stdin.write(json.dumps(payload) + "\n")
    process.stdin.flush()
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RequestTimeout(payload["method"])
        try:
            message = messages.get(timeout=remaining)
        except queue.Empty as error:
            raise RequestTimeout(payload["method"]) from error
        if message.get("id") == payload["id"]:
            return message
        if pending is not None:
            pending.append(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--run", action="store_true", help="start one model turn")
    args = parser.parse_args()
    codex = args.codex.resolve(strict=True)
    state = args.state_dir.resolve(strict=True)
    require_outside_git_worktree(state)
    private_home = state / "home"
    codex_home = state / "codex-home"
    if not (codex_home / "auth.json").is_file():
        raise ValueError("private file-backed auth is missing")
    project = state / "project"
    skill_dir = project / ".agents" / "skills" / SKILL_NAME
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {SKILL_NAME}\ndescription: Synthetic native-selection test.\n---\n\n"
        f"When invoked, reply with exactly {MARKER}. Do not call any tools.\n",
        encoding="utf-8",
    )
    personal = Path.home()
    roots = [personal / ".agents" / "skills", personal / ".codex" / "skills",
             personal / ".codex" / "sessions", personal / ".codex" / "auth.json"]
    before = [hash_path(root) for root in roots]
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    env = {
        "HOME": str(private_home), "USERPROFILE": str(private_home),
        "HOMEDRIVE": private_home.drive,
        "HOMEPATH": str(private_home)[len(private_home.drive):],
        "CODEX_HOME": str(codex_home),
        "APPDATA": str(state / "appdata"),
        "LOCALAPPDATA": str(state / "localappdata"),
        "TEMP": str(state), "TMP": str(state),
        "SystemRoot": system_root, "WINDIR": system_root,
        "PATH": os.pathsep.join([str(codex.parent), str(Path(system_root) / "System32")]),
    }
    error_log = (state / "app-server.stderr.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [str(codex), "app-server", "--stdio"], cwd=project, env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=error_log,
        text=True, encoding="utf-8",
    )
    messages = queue.Queue()
    pending = []
    threading.Thread(target=read_lines, args=(process.stdout, messages), daemon=True).start()
    summary = {"model_calls": 0}
    try:
        init = request(process, messages, {"method": "initialize", "id": 1,
            "params": {"clientInfo": {"name": "laomedo_feasibility",
                                      "title": "Laomedo Feasibility Probe", "version": "0.1.0"}}}, pending)
        summary["initialized"] = "result" in init
        if not summary["initialized"]:
            summary["initialize_error_code"] = init.get("error", {}).get("code")
            return print(json.dumps(summary, indent=2))
        process.stdin.write(json.dumps({"method": "initialized", "params": {}}) + "\n")
        process.stdin.flush()
        found = request(process, messages, {"method": "skills/list", "id": 2,
            "params": {"cwds": [str(project)], "forceReload": True}}, pending)
        skills = found.get("result", {}).get("data", [{}])[0].get("skills", [])
        summary["fixture_discovered"] = any(x.get("name") == SKILL_NAME for x in skills)
        summary["other_skill_count"] = sum(x.get("name") != SKILL_NAME for x in skills)
        summary["skills_outside_private_state"] = sum(
            not Path(x.get("path", "C:/missing")).resolve().is_relative_to(state)
            for x in skills
        )
        models = request(process, messages, {"method": "model/list", "id": 3,
            "params": {"limit": 100}}, pending)
        summary["model_list_ok"] = "result" in models
        summary["model_list_error_code"] = models.get("error", {}).get("code")
        data = models.get("result", {}).get("data", [])
        summary["model_count"] = len(data)
        summary["model_ids"] = [x.get("id") or x.get("model") for x in data]
        selected = next((x for x in data if (x.get("id") or x.get("model")) == "gpt-6-luna"), None)
        if not selected:
            defaults = [x for x in data if x.get("isDefault")]
            selected = defaults[0] if defaults else (data[0] if data else {})
        model = selected.get("id") or selected.get("model")
        summary["selected_model"] = model
        efforts = selected.get("supportedReasoningEfforts", [])
        summary["supported_efforts"] = [x.get("reasoningEffort", x) if isinstance(x, dict) else x for x in efforts]
        try:
            with socket.create_connection(("chatgpt.com", 443), timeout=3):
                summary["chatgpt_tcp_reachable"] = True
        except OSError as error:
            summary["chatgpt_tcp_reachable"] = False
            summary["chatgpt_tcp_error_type"] = type(error).__name__
        if not args.run:
            return print(json.dumps(summary, indent=2))
        if (not summary["fixture_discovered"] or not model or
                summary["skills_outside_private_state"] or
                not summary["chatgpt_tcp_reachable"]):
            summary["blocked_before_turn"] = True
            return print(json.dumps(summary, indent=2))
        start = request(process, messages, {"method": "thread/start", "id": 4,
            "params": {"model": model, "cwd": str(project), "approvalPolicy": "never",
                       "config": {"model_reasoning_effort": "low"},
                       "sandbox": "read-only"}}, pending, timeout=30)
        if "result" not in start:
            summary["thread_start_error_code"] = start.get("error", {}).get("code")
            return print(json.dumps(summary, indent=2))
        thread_id = start["result"].get("thread", {}).get("id")
        if not thread_id:
            summary["thread_id_missing"] = True
            return print(json.dumps(summary, indent=2))
        summary["selection_mode"] = "explicit_combined_text_and_skill_item"
        summary["model_calls"] = 1
        turn = request(process, messages, {"method": "turn/start", "id": 5,
            "params": {"threadId": thread_id,
                       "input": [{"type": "text", "text": "$fixture-native-119 Reply according to the selected skill."},
                                 {"type": "skill", "name": SKILL_NAME,
                                  "path": str(skill_dir / "SKILL.md")}] }}, pending, timeout=30)
        if "result" not in turn:
            summary["turn_start_error_code"] = turn.get("error", {}).get("code")
            return print(json.dumps(summary, indent=2))
        output = []
        methods = {}
        status = None
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if pending:
                message = pending.pop(0)
            else:
                try:
                    message = messages.get(timeout=1)
                except queue.Empty:
                    continue
            method = message.get("method", "")
            methods[method] = methods.get(method, 0) + 1
            params = message.get("params", {})
            if method in ("item/completed", "item/updated", "item/started"):
                item = params.get("item", {})
                if item.get("type") == "agentMessage":
                    output.append(item.get("text", ""))
            if method == "turn/completed":
                status = params.get("turn", {}).get("status")
                break
        summary["turn_status"] = status or "timeout"
        summary["marker_returned"] = any(MARKER in x for x in output)
        summary["agent_message_observed"] = bool(output)
        summary["event_methods"] = {k: v for k, v in methods.items() if k in
            ("item/started", "item/updated", "item/completed", "turn/completed", "thread/tokenUsage/updated")}
        summary["other_event_methods"] = sorted(k for k in methods if k not in summary["event_methods"])
        print(json.dumps(summary, indent=2))
    except RequestTimeout as error:
        summary["request_timeout_stage"] = error.method
        summary["turn_status"] = "request_timeout" if summary["model_calls"] else "not_started"
        print(json.dumps(summary, indent=2))
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        error_log.close()
        error_text = (state / "app-server.stderr.log").read_text(encoding="utf-8", errors="replace").lower()
        print(json.dumps({"stderr_signals": {
            "authentication": any(x in error_text for x in ("auth", "unauthorized", "token expired")),
            "network": any(x in error_text for x in ("connection", "network", "dns", "timeout")),
            "sandbox": "sandbox" in error_text,
            "nonempty": bool(error_text.strip()),
        }}, indent=2))
        after = [hash_path(root) for root in roots]
        print(json.dumps({"personal_roots_unchanged": dict(zip(
            ["user_skills", "codex_skills", "codex_sessions", "codex_auth"],
            (a == b for a, b in zip(before, after))))}, indent=2))


if __name__ == "__main__":
    main()
