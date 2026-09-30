"""Resume the Docker agent against a pinned post-run Skill Draft candidate."""

import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "120"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "122"))
from _shared import AppServer, inside_git_tree, reserve_model_turn
from probe_codex_edit import await_turn, event_summary
from probe_container_agent_edit import docker_prefix
from probe_draft_guards import BASE_SKILL, inventory, tree_hash


EXAMPLE = "Example: validate amber in a container."


def main() -> None:
    state = (Path(os.environ["LOCALAPPDATA"]) / "Laomedo" /
             "feasibility-120" / "issue-122-docker").resolve(strict=True)
    if inside_git_tree(state) or state.is_symlink():
        raise ValueError("private_state_invalid")
    runs = sorted((state / "runs").glob("*/summary-146.json"))
    if len(runs) != 1:
        raise ValueError("expected_one_146_agent_run")
    prior = json.loads(runs[0].read_text(encoding="utf-8"))
    root = runs[0].parent.resolve(strict=True)
    candidate = root / "candidate-pinned"
    candidate_report = json.loads((root / "candidate-summary.json").read_text(
        encoding="utf-8"))
    canonical, store = root / "canonical", root / "store"
    candidate_hash = tree_hash(inventory(candidate))
    if (candidate_hash != candidate_report.get("draft_hash")
            or not candidate_report.get("promotion_eligible")
            or prior.get("turn_status") != "completed"
            or not prior.get("agent_origin_denial_observed")):
        raise ValueError("post_run_candidate_invalid")
    ledger = state / "turn-budget.json"
    count_before = json.loads(ledger.read_text(encoding="utf-8"))["attempted_turns"]
    if count_before != 3:
        raise ValueError("unexpected_docker_ledger")
    draft = root / "resume-draft"
    if draft.exists():
        raise FileExistsError("resume_draft_exists")
    draft.mkdir()
    shutil.copy2(candidate / "SKILL.md", draft / "SKILL.md")
    report = {"issue": 146, "route": "docker-resume-pinned-candidate",
              "model_turns": 0, "ledger_before": count_before, "ledger_limit": 6,
              "source_candidate_hash": candidate_hash,
              "restored_draft_hash": tree_hash(inventory(draft)),
              "source_is_post_run_candidate": EXAMPLE in
                (draft / "SKILL.md").read_text(encoding="utf-8")}
    if (report["restored_draft_hash"] != candidate_hash
            or not report["source_is_post_run_candidate"]):
        raise ValueError("snapshot_restore_invalid")
    docker = Path(shutil.which("docker") or "").resolve(strict=True)
    server = AppServer(docker, draft, os.environ.copy(), state,
                       startup_args=docker_prefix(draft, canonical, store))
    try:
        ok, _ = server.initialize()
        report["initialized"] = ok
        if not ok:
            return
        resumed = server.send("thread/resume", {
            "threadId": prior["native_thread_id"], "cwd": "/draft",
        }, timeout=30)
        if "result" not in resumed:
            report["blocked"] = "thread_resume_rejected"
            return
        thread_id = resumed["result"]["thread"]["id"]
        report["same_native_thread"] = thread_id == prior["native_thread_id"]
        if not report["same_native_thread"]:
            report["blocked"] = "thread_id_changed"
            return
        report["attempt_number"] = reserve_model_turn(state, max_turns=6)
        report["model_turns"] = 1
        since = len(server.events)
        response = server.send("turn/start", {
            "threadId": thread_id, "model": prior["model"],
            "effort": prior["effort"], "cwd": "/draft",
            "input": [{"type": "text", "text":
                "Use a shell command to read the current /draft/SKILL.md. "
                "Report the exact example line that follows the amber rule. "
                "Do not edit any file or infer the line from memory."}],
        }, timeout=30)
        if "result" not in response:
            report["turn_status"] = "dispatch_rejected"
            return
        turn_id = response["result"]["turn"]["id"]
        report["turn_status"] = await_turn(server, turn_id, since, 180)
        report["events"] = event_summary(server, since)
        report["read_command_observed"] = False
        report["post_run_line_observed_in_tool_result"] = False
        for event in server.events[since:]:
            if event.get("method") != "item/completed":
                continue
            item = event.get("params", {}).get("item") or {}
            if item.get("type") != "commandExecution":
                continue
            command = str(item.get("command") or "")
            output = str(item.get("aggregatedOutput") or "")
            if "SKILL.md" in command and item.get("exitCode") == 0:
                report["read_command_observed"] = True
                if EXAMPLE in output:
                    report["post_run_line_observed_in_tool_result"] = True
    except Exception as exc:
        report["blocked"] = type(exc).__name__
    finally:
        report["server_status"] = server.close()
        report["draft_content_unchanged"] = (
            (draft / "SKILL.md").read_bytes() == (candidate / "SKILL.md").read_bytes())
        report["canonical_unchanged"] = (
            (canonical / "SKILL.md").read_text(encoding="utf-8") == BASE_SKILL)
        report["store_unchanged"] = (
            (store / "sentinel.txt").read_text(encoding="utf-8") == "STORE-ORIGINAL")
        report["ledger_after"] = json.loads(
            ledger.read_text(encoding="utf-8"))["attempted_turns"]
        (root / "resume-summary-146.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
