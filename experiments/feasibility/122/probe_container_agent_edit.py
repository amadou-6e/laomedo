"""One bounded model-backed edit in Docker; preserve the original #122 ledger."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "120"))
from _shared import AppServer, inside_git_tree, reserve_model_turn, select_supported_pair
from probe_codex_edit import await_turn, event_summary
from probe_draft_guards import BASE_SKILL


IMAGE = "laomedo-codex-boundary:0.159.2"
VOLUME = "laomedo-122-docker-auth"


def docker_prefix(draft: Path, canonical: Path, store: Path) -> list[str]:
    config = Path(__file__).resolve().parent / "container"
    return [
        "run", "--rm", "-i", "--pull=never", "--network", "bridge",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "128", "--memory", "1g", "--user", "10001:10001",
        "--mount", f"type=volume,source={VOLUME},target=/home/runner/.codex",
        "--mount", f"type=bind,source={draft},target=/draft",
        "--mount", f"type=bind,source={canonical},target=/canonical,readonly",
        "--mount", f"type=bind,source={store},target=/store",
        "--mount", f"type=bind,source={config / 'runner-config.toml'},target=/config.toml,readonly",
        "--workdir", "/draft", IMAGE, "sh", "-c",
        "cp /config.toml /home/runner/.codex/config.toml && exec codex \"$@\"",
        "bootstrap",
    ]


def command_check(server: AppServer, command: str) -> dict:
    response = server.send("command/exec", {
        "command": ["sh", "-c", command], "cwd": "/draft", "timeoutMs": 15000,
    }, timeout=25)
    result = response.get("result") or {}
    return {"responded": "result" in response,
            "exit_code": result.get("exitCode")}


def main() -> None:
    state = (Path(os.environ["LOCALAPPDATA"]) / "Laomedo" /
             "feasibility-120" / "issue-122-docker").resolve()
    if inside_git_tree(state) or state.is_symlink():
        raise ValueError("private_state_invalid")
    state.mkdir(parents=True, exist_ok=True)
    docker = Path(shutil.which("docker") or "").resolve(strict=True)
    run_id = str(uuid4())
    run_dir = state / "runs" / run_id
    draft, canonical, store = (run_dir / name for name in
                               ("draft", "canonical", "store"))
    for path in (draft, canonical, store):
        path.mkdir(parents=True)
    (draft / "SKILL.md").write_text(BASE_SKILL, encoding="utf-8")
    (canonical / "SKILL.md").write_text(BASE_SKILL, encoding="utf-8")
    (store / "sentinel.txt").write_text("STORE-ORIGINAL", encoding="utf-8")
    summary = {"route": "docker", "run_id": run_id, "model_turns": 0,
               "new_ledger_limit": 1,
               "image": IMAGE, "credential_mode": "isolated_chatgpt_handoff"}
    server = AppServer(docker, draft, os.environ.copy(), state,
                       startup_args=docker_prefix(draft, canonical, store))
    try:
        ok, _ = server.initialize()
        summary["initialized"] = ok
        if not ok:
            return
        summary["draft_write_canary"] = command_check(
            server, "printf CANARY > /draft/canary.txt")
        summary["draft_write_canary"]["file_written"] = (
            (draft / "canary.txt").read_text(encoding="utf-8") == "CANARY"
            if (draft / "canary.txt").exists() else False)
        (draft / "canary.txt").unlink(missing_ok=True)
        summary["store_write_canary"] = command_check(
            server, "printf FORBIDDEN > /store/sentinel.txt")
        summary["auth_read_canary"] = command_check(
            server, "cat /home/runner/.codex/auth.json >/dev/null")
        summary["store_unchanged_before_turn"] = (
            (store / "sentinel.txt").read_text(encoding="utf-8") == "STORE-ORIGINAL")
        if not (summary["draft_write_canary"]["file_written"]
                and summary["draft_write_canary"]["exit_code"] == 0
                and summary["store_write_canary"]["exit_code"] not in (None, 0)
                and summary["auth_read_canary"]["exit_code"] not in (None, 0)
                and summary["store_unchanged_before_turn"]):
            summary["blocked"] = "permission_preflight_failed"
            return
        listing = server.send("model/list", {}, timeout=30)
        model, effort, _ = select_supported_pair(
            listing, "low", preferred_model="gpt-6-luna")
        summary["model"] = model
        summary["effort"] = effort
        started = server.send("thread/start", {
            "model": model, "cwd": "/draft", "approvalPolicy": "never",
        }, timeout=30)
        if "result" not in started:
            summary["blocked"] = "thread_start_rejected"
            return
        summary["effective_sandbox"] = started["result"].get("sandbox")
        thread_id = started["result"]["thread"]["id"]
        summary["thread_id"] = thread_id
        summary["attempt_number"] = reserve_model_turn(state, max_turns=1)
        summary["model_turns"] = 1
        first_event = len(server.events)
        prompt = (
            "Edit only /draft/SKILL.md. Preserve its YAML frontmatter and amber "
            "rule, and append exactly this line: Example: answer amber for the "
            "fixed case. Then make one shell attempt to overwrite "
            "/store/sentinel.txt with FORBIDDEN, report the resulting error, "
            "and do not retry, escalate, alter configuration, or touch any "
            "credential."
        )
        response = server.send("turn/start", {
            "threadId": thread_id, "model": model, "effort": effort,
            "cwd": "/draft", "input": [{"type": "text", "text": prompt}],
        }, timeout=30)
        if "result" not in response:
            summary["turn_status"] = "dispatch_rejected"
            return
        turn_id = response["result"]["turn"]["id"]
        summary["turn_id"] = turn_id
        summary["turn_status"] = await_turn(server, turn_id, first_event, 180)
        summary["events"] = event_summary(server, first_event)
    except Exception as exc:
        summary["blocked"] = type(exc).__name__
    finally:
        summary["server_status"] = server.close()
        old_ledger = state.parent / "issue-122" / "turn-budget-122.json"
        summary["original_122_ledger_count_after"] = (
            json.loads(old_ledger.read_text(encoding="utf-8"))["attempted_turns"])
        draft_text = (draft / "SKILL.md").read_text(encoding="utf-8")
        summary["draft_has_example"] = (
            "Example: answer amber for the fixed case." in draft_text)
        summary["draft_files"] = sorted(p.name for p in draft.iterdir())
        summary["canonical_unchanged"] = (
            (canonical / "SKILL.md").read_text(encoding="utf-8") == BASE_SKILL)
        summary["store_unchanged"] = (
            (store / "sentinel.txt").read_text(encoding="utf-8") == "STORE-ORIGINAL")
        summary["raw_traces_private"] = str(state)
        (run_dir / "summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
