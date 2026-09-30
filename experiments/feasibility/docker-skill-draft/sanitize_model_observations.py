"""Export whitelisted #146 model facts, never raw events or credentials."""

import json
import os
from pathlib import Path


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def last_usage(summary: dict) -> dict:
    updates = summary.get("events", {}).get("token_usage_updates") or []
    return updates[-1] if updates else {}


def main() -> None:
    state = (Path(os.environ["LOCALAPPDATA"]) / "Laomedo" /
             "feasibility-120" / "issue-122-docker").resolve(strict=True)
    runs = list((state / "runs").glob("*/summary-146.json"))
    if len(runs) != 1:
        raise ValueError("expected_one_146_agent_run")
    root = runs[0].parent
    agent = read(runs[0])
    candidate = read(root / "candidate-summary.json")
    resume = read(root / "resume-summary-146.json")
    docker_ledger = read(state / "turn-budget.json")["attempted_turns"]
    original_ledger = read(state.parent / "issue-122" /
                           "turn-budget-122.json")["attempted_turns"]
    report = {
        "issue": 146,
        "credential_mode": "isolated_chatgpt_handoff_in_private_docker_volume",
        "raw_traces": "private_only",
        "original_122_attempts": original_ledger,
        "docker_route_attempts": docker_ledger,
        "docker_route_cap": 6,
        "policy_ref": agent["policy_ref"],
        "base_hash": agent["base_hash"],
        "agent_edit_and_denial": {
            "attempt": agent["attempt_number"],
            "run_id": agent["run_id"],
            "native_thread_id": agent["native_thread_id"],
            "native_turn_id": agent["native_turn_id"],
            "model": agent["model"],
            "effort": agent["effort"],
            "turn_status": agent["turn_status"],
            "item_type_counts": agent["events"]["item_type_counts"],
            "command_evidence": agent["command_evidence"],
            "agent_origin_denial_observed": agent["agent_origin_denial_observed"],
            "canonical_unchanged": agent["canonical_unchanged"],
            "store_unchanged": agent["store_unchanged"],
            "token_usage": last_usage(agent),
        },
        "candidate": {
            "skipped_empty_runtime_dirs": candidate["skipped_empty_runtime_dirs"],
            "changed_paths": candidate["changed_paths"],
            "base_hash": candidate["base_hash"],
            "draft_hash": candidate["draft_hash"],
            "patch_available": candidate["patch_available"],
            "violations": candidate["violations"],
            "fixed_case_passed": candidate["fixed_case_passed"],
            "promotion_eligible_for_review": candidate["promotion_eligible"],
        },
        "resume": {
            "attempt": resume["attempt_number"],
            "turn_status": resume["turn_status"],
            "same_native_thread": resume["same_native_thread"],
            "restored_draft_hash": resume["restored_draft_hash"],
            "source_candidate_hash": resume["source_candidate_hash"],
            "read_command_observed": resume["read_command_observed"],
            "post_run_line_observed_in_tool_result":
                resume["post_run_line_observed_in_tool_result"],
            "draft_content_unchanged": resume["draft_content_unchanged"],
            "canonical_unchanged": resume["canonical_unchanged"],
            "store_unchanged": resume["store_unchanged"],
            "token_usage": last_usage(resume),
        },
    }
    output = Path(__file__).resolve().parent / "model-observations.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": output.name,
                      "docker_route_attempts": docker_ledger,
                      "agent_origin_denial_observed":
                          report["agent_edit_and_denial"]["agent_origin_denial_observed"],
                      "resume_same_thread": report["resume"]["same_native_thread"]}))


if __name__ == "__main__":
    main()
