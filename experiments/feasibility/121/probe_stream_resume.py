"""Probe Claude Agent SDK streaming, skill invocation, failure, cancellation,
and resume.

Credential required: the credential gate must pass before any model call.
Tests:
- Streamed messages contain a tool call (ToolUseBlock) and its matching result
  (ToolResultBlock with the same tool_use_id).
- Continuity: run 1 reads a synthetic code from the workspace; run 2 resumes
  in a fresh CLI process and must return the code without re-reading it. The
  code is a fixed synthetic marker, so the check leaks nothing.
- Skill invocation: a listed skill is invoked as a Skill tool use; an unlisted
  skill is refused by the Skill tool; the unlisted skill's files stay readable
  with Read, as the reference documents.
- Failure: an invalid model fails explicitly. Cancellation via interrupt()
  ends with terminal_reason aborted_*.
- Resuming an unknown session id fails explicitly.
- The workspace is fingerprinted before and after; the probe records that the
  SDK persists conversation only, so restoring the last post-run workspace
  snapshot is the Laomedo runner's responsibility.

Every credentialed call is bounded by max_turns and max_budget_usd.
"""

import argparse
import asyncio
import json
from pathlib import Path
import sys
import time

PROJECT_SKILL = "fixture-121-stream"
MARKER = "LAOMEDO-121-READY"


async def collect_query(prompt, options, summary, label, marker=None,
                        timeout_s=180):
    """One-shot query() with a wall-clock deadline. Returns collected events."""
    from claude_agent_sdk._errors import (CLIConnectionError, CLINotFoundError,
                                          ProcessError, ResultError)
    from _shared import collect_events, count_attempted_turn

    messages = []
    outcome = {}
    count_attempted_turn(summary)
    deadline = time.monotonic() + timeout_s
    try:
        async for message in _query(prompt, options):
            messages.append(message)
            if time.monotonic() > deadline:
                outcome["deadline_exceeded"] = True
                break
    except (CLINotFoundError, CLIConnectionError) as exc:
        outcome["outcome"] = "cli_unavailable"
        outcome["error"] = type(exc).__name__
    except ResultError as exc:
        outcome["outcome"] = "result_error"
        outcome["subtype"] = getattr(exc, "subtype", None)
        outcome["terminal_reason"] = getattr(exc, "terminal_reason", None)
        outcome["errors"] = getattr(exc, "errors", None)
        outcome["api_error_status"] = getattr(exc, "api_error_status", None)
    except ProcessError as exc:
        outcome["outcome"] = "process_error"
        outcome["exit_code"] = getattr(exc, "exit_code", None)
        outcome["error"] = type(exc).__name__
    except Exception as exc:
        outcome["outcome"] = "other_error"
        outcome["error"] = f"{type(exc).__name__}: {exc}"
    collected = collect_events(messages, marker=marker)
    summary[label] = {**outcome, **collected}
    return summary[label]


async def _query(prompt, options):
    from claude_agent_sdk import query
    async for message in query(prompt=prompt, options=options):
        yield message


async def run_interrupt(project, private_home, config_dir, state, summary):
    """Start a long turn, interrupt it, and drain to its ResultMessage."""
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage
    from claude_agent_sdk._errors import CLIConnectionError, CLINotFoundError
    from _shared import collect_events, count_attempted_turn, options_env

    options = ClaudeAgentOptions(
        cwd=str(project),
        env=options_env(private_home, config_dir, state),
        setting_sources=["project"],
        max_turns=1,
        max_budget_usd=1.0,
        permission_mode="default",
        allowed_tools=["Bash"],
    )
    count_attempted_turn(summary)
    outcome = {}
    messages = []
    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query("Run the command: sleep 60. Then reply done.")
            await asyncio.sleep(5)
            await client.interrupt()
            async for message in client.receive_response():
                messages.append(message)
                if isinstance(message, ResultMessage):
                    break
    except (CLINotFoundError, CLIConnectionError) as exc:
        summary["cancellation"] = {"outcome": "cli_unavailable",
                                   "error": type(exc).__name__}
        return
    except Exception as exc:
        outcome["outcome"] = "other_error"
        outcome["error"] = f"{type(exc).__name__}: {exc}"
        summary["cancellation"] = {**outcome, **collect_events(messages)}
        return
    collected = collect_events(messages)
    result = collected.get("result") or {}
    outcome.update({
        "interrupt_observed": result.get("terminal_reason") in
                              ("aborted_streaming", "aborted_tools"),
        "terminal_reason": result.get("terminal_reason"),
        "subtype": result.get("subtype"),
    })
    summary["cancellation"] = {**outcome, **collected}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True,
                        help="new or empty private state dir outside any git tree")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _shared import (compare_personal_roots, credential_gate, fingerprint,
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

    private_home = state / "home"
    config_dir = state / "claude-config"
    project = state / "project"
    for directory in (private_home, config_dir, project):
        directory.mkdir(parents=True, exist_ok=True)
    (project / "notes.txt").write_text(
        f"The launch code is {MARKER}.\n", encoding="utf-8")
    write_skill(project / ".claude" / "skills", PROJECT_SKILL,
                "Synthetic streaming fixture for issue 121. Reply READY when invoked.")
    # An unlisted decoy for the refusal test.
    write_skill(project / ".claude" / "skills", "fixture-121-unlisted",
                "Synthetic unlisted fixture for issue 121.")

    gate = credential_gate(state, config_dir)
    summary["credential_gate"] = gate
    if not gate.get("permitted"):
        print(json.dumps(summary, indent=2))
        return

    before = hash_personal_roots()

    try:
        from claude_agent_sdk import ClaudeAgentOptions
        from _shared import options_env

        def make_options(resume=None, skills=(PROJECT_SKILL,)):
            return ClaudeAgentOptions(
                cwd=str(project),
                env=options_env(private_home, config_dir, state),
                setting_sources=["project"],
                skills=list(skills),
                max_turns=3,
                max_budget_usd=1.25,
                permission_mode="default",
                allowed_tools=["Read", "Glob", "Grep"],
                resume=resume,
            )

        # Run 1: streamed tool call and matching result, returning the marker.
        run1 = asyncio.run(collect_query(
            "Read the file notes.txt in the project directory, then reply with "
            "exactly the launch code it contains.",
            make_options(), summary, "run1_stream", marker=MARKER))
        summary["workspace_hash_run1"] = fingerprint(project)
        session_id = ((run1.get("result") or {}).get("session_id")
                      or (run1.get("init") or {}).get("session_id"))
        summary["run1_session_id"] = session_id

        if session_id:
            # Run 2: resume in a fresh CLI process (a new query() process is
            # the runner restart). Continuity is proven by the marker coming
            # back without re-reading the file.
            run2 = asyncio.run(collect_query(
                "Without reading any file, reply with exactly the launch code "
                "you read earlier.",
                make_options(resume=session_id), summary, "run2_resume",
                marker=MARKER))
            summary["run2_session_id"] = ((run2.get("result") or {}).get("session_id")
                                          or (run2.get("init") or {}).get("session_id"))
            summary["resume_same_session"] = (summary["run2_session_id"] == session_id)
            summary["resume_continuity_marker"] = run2.get("marker_returned")

        # Skill invocation: listed skill is invoked; unlisted is refused.
        asyncio.run(collect_query(
            "Use the fixture-121-stream skill, then reply with its READY line.",
            make_options(), summary, "skill_listed_invoked"))
        skill_runs = asyncio.run(_skill_pair(
            project, private_home, config_dir, state, make_options, summary))

        # Unavailable session: resume a fabricated id must fail explicitly.
        asyncio.run(collect_query(
            "Reply with ok.",
            make_options(resume="00000000-0000-4000-8000-000000000000"),
            summary, "resume_unknown_session"))

        # Failure: an invalid model must fail explicitly.
        options_bad = make_options()
        options_bad.model = "nonexistent-model-121"
        asyncio.run(collect_query(
            "Reply with ok.", options_bad, summary, "failure_invalid_model"))

        # Cancellation.
        asyncio.run(run_interrupt(project, private_home, config_dir, state, summary))

        summary["workspace_hash_final"] = fingerprint(project)
        summary["workspace_changed"] = summary["workspace_hash_run1"] != summary["workspace_hash_final"]
        summary["note"] = ("The SDK persists conversation history only; restoring "
                           "the last post-run workspace snapshot is the Laomedo "
                           "runner registry's responsibility (see 121.md).")
    finally:
        costs = [entry["result"]["total_cost_usd"]
                 for entry in summary.values()
                 if isinstance(entry, dict) and isinstance(entry.get("result"), dict)
                 and entry["result"].get("total_cost_usd") is not None]
        summary["observed_cost_usd"] = round(sum(costs), 6) if costs else None
        summary["model_calls_note"] = ("upper bound on billable model calls: a "
                                       "turn is counted when submitted, before "
                                       "any response; max_budget_usd is checked "
                                       "between turns, so one turn can exceed it")
        summary["personal_roots_unchanged"] = compare_personal_roots(
            before, hash_personal_roots())
        print(json.dumps(summary, indent=2))


async def _skill_pair(project, private_home, config_dir, state, make_options,
                      summary):
    """Listed skill: expect a Skill tool use. Unlisted skill: expect the Skill
    tool to refuse while Read still reaches the files."""
    unlisted = await collect_query(
        "Use the fixture-121-unlisted skill.",
        make_options(skills=(PROJECT_SKILL,)), summary,
        "skill_unlisted_refused")
    unlisted_calls = unlisted.get("tool_call_names") or []
    errors = unlisted.get("tool_result_errors") or {}
    matched = unlisted.get("tool_results_matched") or []
    summary["skill_unlisted_refused"]["unlisted_skill_refused"] = bool(
        "Skill" in unlisted_calls and matched
        and any(errors.get(tool_id) for tool_id in matched))
    read_run = await collect_query(
        "Read the file .claude/skills/fixture-121-unlisted/SKILL.md with the "
        "Read tool, then reply done.",
        make_options(skills=[]), summary, "unlisted_readable_via_read")
    summary["unlisted_readable_via_read"] = {
        "read_observed": "Read" in (read_run.get("tool_call_names") or []),
        "outcome": read_run.get("outcome"),
    }
    return unlisted, read_run


if __name__ == "__main__":
    main()
