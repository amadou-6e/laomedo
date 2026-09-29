"""Probe Claude Agent SDK setting sources, skill isolation, and model/effort
settings.

Credential required: the credential gate must pass before any model call.
Tests:
- setting_sources=[] loads no skills; ["user", "project"] loads decoys planted
  in the private HOME and the private project; ["project"] loads only the
  project decoy.
- The init message's skills array and data keys are recorded.
- Requested model/effort versus effective model (AssistantMessage.model and
  ResultMessage.model_usage keys).
- An invalid effort value and an invalid model fail explicitly.
- Personal profile roots are unchanged.

Every credentialed call is bounded by max_turns=1 and max_budget_usd from the
spend rule.
"""

import asyncio
import json
import os
from pathlib import Path
import sys


PROJECT_SKILL = "fixture-121-project"
HOME_SKILL = "fixture-121-user"


async def run_query(state, private_home, config_dir, prompt, summary, label,
                    setting_sources, skills, model=None, effort=None):
    from claude_agent_sdk import ClaudeAgentOptions
    from claude_agent_sdk._errors import (CLIConnectionError, CLINotFoundError,
                                          ProcessError, ResultError)
    from _shared import options_env, collect_events, count_attempted_turn

    options = ClaudeAgentOptions(
        cwd=str(state),
        env=options_env(private_home, config_dir),
        setting_sources=setting_sources,
        skills=skills,
        max_turns=1,
        max_budget_usd=1.0,
        permission_mode="default",
        allowed_tools=["Read", "Glob", "Grep"],
    )
    if model:
        options.model = model
    if effort:
        options.effort = effort

    messages = []
    outcome = {}
    # Counted on submission: an attempted turn is an upper bound on billable
    # model calls even when the request is rejected before generation.
    count_attempted_turn(summary)
    try:
        async for message in query_messages(prompt, options):
            messages.append(message)
    except (CLINotFoundError, CLIConnectionError) as exc:
        outcome["outcome"] = "cli_unavailable"
        outcome["error"] = type(exc).__name__
    except ResultError as exc:
        outcome["outcome"] = "result_error"
        outcome["subtype"] = getattr(exc, "subtype", None)
        outcome["terminal_reason"] = getattr(exc, "terminal_reason", None)
        outcome["errors"] = getattr(exc, "errors", None)
    except ProcessError as exc:
        outcome["outcome"] = "process_error"
        outcome["exit_code"] = getattr(exc, "exit_code", None)
        outcome["error"] = type(exc).__name__
    except ValueError as exc:
        outcome["outcome"] = "rejected_client_side"
        outcome["error"] = f"ValueError: {exc}"
    except Exception as exc:
        outcome["outcome"] = "other_error"
        outcome["error"] = f"{type(exc).__name__}: {exc}"
    collected = collect_events(messages)
    summary[label] = {**outcome, **collected}
    return summary[label]


async def query_messages(prompt, options):
    from claude_agent_sdk import query
    async for message in query(prompt=prompt, options=options):
        yield message


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True,
                        help="private state dir outside any git tree")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _shared import (compare_personal_roots, credential_gate, hash_personal_roots,
                          options_env, personal_roots, resettable_dir,
                          runner_versions, write_skill)

    state, leftovers = resettable_dir(args.state_dir.resolve())
    private_home = state / "home"
    config_dir = state / "claude-config"
    project = state / "project"
    for directory in (private_home, config_dir, project):
        directory.mkdir(parents=True, exist_ok=True)
    (project / "notes.txt").write_text("probe fixture\n", encoding="utf-8")
    write_skill(project / ".claude" / "skills", PROJECT_SKILL,
                "Synthetic project fixture for issue 121.")
    write_skill(private_home / ".claude" / "skills", HOME_SKILL,
                "Synthetic user fixture for issue 121.")

    summary = dict(runner_versions())
    summary["scratch_leftovers"] = leftovers
    gate = credential_gate(state, config_dir)
    summary["credential_gate"] = gate
    if not gate.get("permitted"):
        print(json.dumps(summary, indent=2))
        return

    before = hash_personal_roots()

    try:
        # Source control: which decoys appear under each setting_sources value.
        for label, sources in [
            ("sources_empty", []),
            ("sources_user_project", ["user", "project"]),
            ("sources_project_only", ["project"]),
        ]:
            run_query_compat = run_query
            asyncio.run(run_query_compat(
                state, private_home, config_dir,
                "Reply with the single word ready. Do not use any tools.",
                summary, label, sources, "all"))

        # Requested versus effective model/effort.
        asyncio.run(run_query(
            state, private_home, config_dir,
            "Reply with the single word ready. Do not use any tools.",
            summary, "supported_model_effort", ["project"], "all",
            model="claude-haiku-4-5", effort="low"))

        # Unsupported settings must fail explicitly.
        asyncio.run(run_query(
            state, private_home, config_dir,
            "Reply with the single word ready. Do not use any tools.",
            summary, "invalid_effort", ["project"], "all",
            model="claude-haiku-4-5", effort="superultra"))
        asyncio.run(run_query(
            state, private_home, config_dir,
            "Reply with the single word ready. Do not use any tools.",
            summary, "invalid_model", ["project"], "all",
            model="nonexistent-model-121"))
    finally:
        costs = [entry["result"]["total_cost_usd"]
                 for entry in summary.values()
                 if isinstance(entry, dict) and isinstance(entry.get("result"), dict)
                 and entry["result"].get("total_cost_usd") is not None]
        summary["observed_cost_usd"] = round(sum(costs), 6) if costs else None
        summary["model_calls_note"] = ("upper bound on billable model calls: a "
                                       "turn is counted when submitted, before "
                                       "any response")
        summary["personal_roots_unchanged"] = compare_personal_roots(
            before, hash_personal_roots())
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
