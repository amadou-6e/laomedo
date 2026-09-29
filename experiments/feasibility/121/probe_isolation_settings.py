"""Probe Claude Agent SDK setting sources, skill isolation, and model/effort
settings.

Credential required: the credential gate must pass before any model call.
Tests:
- setting_sources=[] loads no decoy skills; ["user", "project"] and
  ["project"] select them. User-level decoys are planted in BOTH candidate
  user roots, `<private HOME>/.claude/skills` and
  `$CLAUDE_CONFIG_DIR/skills`, under different names, so a miss identifies
  which root the runner version actually reads.
- A parent-level decoy skill and CLAUDE.md are planted in <state>, which is a
  parent of the working directory <state>/run/project; nothing is written
  outside --state-dir. A parent skill seen in init means leakage. CLAUDE.md loading is
  not observable in the sanitized stream and is recorded as unobservable.
- Requested model/effort versus effective model. The supported pair uses a
  model from the documented effort table; Haiku is the documented-unsupported
  case ("models not listed here do not support effort").
- An invalid effort value and an invalid model fail explicitly.
- Personal profile roots are unchanged (user_projects labeled inconclusive).

Every credentialed call is bounded by max_turns=1 and max_budget_usd.
"""

import argparse
import asyncio
import json
from pathlib import Path
import sys

PROJECT_SKILL = "fixture-121-project"
HOME_SKILL = "fixture-121-user-home"
CONFIG_SKILL = "fixture-121-user-config"
PARENT_SKILL = "fixture-121-parent"
PARENT_CLAUDE_MD = "CLAUDE.md"
MARKER = "LAOMEDO-121-READY"

SUPPORTED_MODEL = "claude-sonnet-4-6"   # documented: supports low..max
UNSUPPORTED_EFFORT_MODEL = "claude-haiku-4-5"  # documented: no effort support


async def run_query(project, private_home, config_dir, state, prompt, summary,
                    label, setting_sources, skills, model=None, effort=None,
                    max_turns=1, budget=0.25):
    from claude_agent_sdk import ClaudeAgentOptions
    from claude_agent_sdk._errors import (CLIConnectionError, CLINotFoundError,
                                          ProcessError, ResultError)
    from _shared import collect_events, count_attempted_turn, options_env

    options = ClaudeAgentOptions(
        cwd=str(project),
        env=options_env(private_home, config_dir, state),
        setting_sources=setting_sources,
        skills=skills,
        max_turns=max_turns,
        max_budget_usd=budget,
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
        async for message in _query(prompt, options):
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


async def _query(prompt, options):
    from claude_agent_sdk import query
    async for message in query(prompt=prompt, options=options):
        yield message


def decoy_state(summary, label, init):
    """Record which decoy skill names the init message reported."""
    if not init:
        return
    names = set(init.get("skill_names") or [])
    summary[label]["decoys_seen"] = sorted(
        name for name in names
        if name in (PROJECT_SKILL, HOME_SKILL, CONFIG_SKILL, PARENT_SKILL))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True,
                        help="new or empty private state dir outside any git tree")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _shared import (compare_personal_roots, credential_gate,
                          hash_personal_roots, prepare_state_dir,
                          runner_versions, write_skill)

    state = args.state_dir.resolve()
    prepared = prepare_state_dir(state)
    summary = dict(runner_versions())
    summary["state_dir"] = prepared
    if prepared.get("refused"):
        summary["credential_gate"] = {"permitted": False,
                                      "reason": prepared["refused"]}
        print(json.dumps(summary, indent=2))
        return

    # Everything lives inside the user-supplied new-or-empty state dir. The
    # run layout sits one level down so the parent-leak decoys can go in
    # <state> itself: a parent of the working directory that this probe
    # created, never a directory outside it.
    run_root = state / "run"
    private_home = run_root / "home"
    config_dir = run_root / "claude-config"
    project = run_root / "project"
    for directory in (private_home, config_dir, project):
        directory.mkdir(parents=True, exist_ok=True)
    (project / "notes.txt").write_text(f"The launch code is {MARKER}.\n",
                                       encoding="utf-8")
    # Decoy skills at both candidate user roots and in the project.
    write_skill(project / ".claude" / "skills", PROJECT_SKILL,
                "Synthetic project fixture for issue 121.")
    write_skill(private_home / ".claude" / "skills", HOME_SKILL,
                "Synthetic user-home fixture for issue 121.")
    write_skill(config_dir / "skills", CONFIG_SKILL,
                "Synthetic config-dir fixture for issue 121.")
    # Parent leakage decoys in <state>, two levels above the working directory.
    (state / PARENT_CLAUDE_MD).write_text("Decoy: must not be loaded.\n", encoding="utf-8")
    write_skill(state / ".claude" / "skills", PARENT_SKILL,
                "Synthetic parent fixture for issue 121.")
    summary["parent_decoys_planted"] = ["CLAUDE.md", PARENT_SKILL]
    summary["parent_decoy_note"] = (
        "Decoys are in the probe's own state dir, a parent of the working "
        "directory; nothing is written outside --state-dir. A parent skill seen "
        "in init means leakage. CLAUDE.md loading is not observable in the "
        "sanitized stream and is recorded as unobservable. Directories above "
        "--state-dir are not tested; use a state root outside the user folder.")

    gate = credential_gate(state, config_dir)
    summary["credential_gate"] = gate
    if not gate.get("permitted"):
        print(json.dumps(summary, indent=2))
        return

    before = hash_personal_roots()

    try:
        source_cases = [
            ("sources_empty", [], "Reply with the single word ready."),
            ("sources_user_project", ["user", "project"],
             "Reply with the single word ready."),
            ("sources_project_only", ["project"],
             "Reply with the single word ready."),
        ]
        for label, sources, prompt in source_cases:
            run = asyncio.run(run_query(
                project, private_home, config_dir, state, prompt, summary,
                label, sources, "all"))
            decoy_state(summary, label, run.get("init"))

        # Supported pair: model and effort both in the documented table.
        run = asyncio.run(run_query(
            project, private_home, config_dir, state,
            "Reply with the single word ready.",
            summary, "supported_model_effort", ["project"], "all",
            model=SUPPORTED_MODEL, effort="low"))
        decoy_state(summary, "supported_model_effort", run.get("init"))

        # Documented-unsupported: Haiku supports no effort levels. Record what
        # the runner does (fallback per the docs, ignore, or error).
        asyncio.run(run_query(
            project, private_home, config_dir, state,
            "Reply with the single word ready.",
            summary, "haiku_with_low_effort", ["project"], "all",
            model=UNSUPPORTED_EFFORT_MODEL, effort="low"))

        # Invalid settings must fail explicitly.
        asyncio.run(run_query(
            project, private_home, config_dir, state,
            "Reply with the single word ready.",
            summary, "invalid_effort", ["project"], "all",
            model=SUPPORTED_MODEL, effort="superultra"))
        asyncio.run(run_query(
            project, private_home, config_dir, state,
            "Reply with the single word ready.",
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
