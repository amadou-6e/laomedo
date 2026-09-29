"""Probe Claude Agent SDK streaming, skill invocation, failure, cancellation,
and resume.

Credential required: the credential gate must pass before any model call.
Tests:
- Streamed messages contain a tool call (ToolUseBlock) and its matching result
  (ToolResultBlock with the same tool_use_id).
- Continuity: run 1 reads a synthetic code from the workspace; run 2 resumes
  in a fresh CLI process and must return the code with no Read call. The
  code is a fixed synthetic marker, so the check leaks nothing.
- Skill invocation: each skill run is classified as not_attempted,
  attempted_refused, attempted_allowed, or attempted_no_result from the Skill
  call's own result. Skill bodies carry markers, so a returned marker shows
  the body ran. Read access to an unlisted skill's files must succeed, and
  /name dispatch of an unlisted skill is recorded because the reference says
  it bypasses the allowlist.
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
UNLISTED_SKILL = "fixture-121-unlisted"
MARKER = "LAOMEDO-121-READY"
LISTED_MARKER = "LISTED-121-RAN"
UNLISTED_MARKER = "UNLISTED-121-RAN"


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
                          runner_versions, skill_attempt, write_skill)

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
                "Synthetic streaming fixture for issue 121.",
                f"When invoked, reply with exactly {LISTED_MARKER}.\n")
    # An unlisted decoy for the refusal and dispatch tests. Its marker appears
    # only in the skill body, so the marker coming back means the body ran.
    write_skill(project / ".claude" / "skills", UNLISTED_SKILL,
                "Synthetic unlisted fixture for issue 121.",
                f"When invoked, reply with exactly {UNLISTED_MARKER}.\n")

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
            # Continuity counts only if the marker came back without a new
            # Read; a re-read would prove file access, not conversation memory.
            reread = "Read" in (run2.get("tool_call_names") or [])
            summary["run2_reread_file"] = reread
            summary["resume_continuity_marker"] = (
                bool(run2.get("marker_returned")) and not reread)

        # Skill invocation: listed skill is invoked; unlisted is refused.
        listed = asyncio.run(collect_query(
            f"Use the {PROJECT_SKILL} skill and follow it.",
            make_options(), summary, "skill_listed_invoked",
            marker=LISTED_MARKER))
        summary["skill_listed_invoked"]["attempt"] = skill_attempt(listed, PROJECT_SKILL)
        asyncio.run(_skill_pair(make_options, summary))

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


async def _skill_pair(make_options, summary):
    """Unlisted skill with only the listed skill allowed: record whether the
    model attempted it (the reference says unlisted skills are hidden from the
    model, so not_attempted is the expected state) and whether its body ran.
    Then check Read access to its files and /name dispatch, which the
    reference says bypasses the allowlist."""
    from _shared import skill_attempt, tool_succeeded

    unlisted = await collect_query(
        f"Use the {UNLISTED_SKILL} skill and follow it.",
        make_options(skills=(PROJECT_SKILL,)), summary,
        "skill_unlisted_refused", marker=UNLISTED_MARKER)
    summary["skill_unlisted_refused"]["attempt"] = skill_attempt(unlisted, UNLISTED_SKILL)
    summary["skill_unlisted_refused"]["unlisted_body_ran"] = bool(
        unlisted.get("marker_returned"))

    read_run = await collect_query(
        f"Read the file .claude/skills/{UNLISTED_SKILL}/SKILL.md with the "
        "Read tool, then reply done.",
        make_options(skills=[]), summary, "unlisted_readable_via_read")
    summary["unlisted_readable_via_read"]["read_attempted"] = (
        "Read" in (read_run.get("tool_call_names") or []))
    summary["unlisted_readable_via_read"]["read_succeeded"] = tool_succeeded(
        read_run, "Read")

    dispatch = await collect_query(
        f"/{UNLISTED_SKILL}",
        make_options(skills=(PROJECT_SKILL,)), summary,
        "unlisted_slash_dispatch", marker=UNLISTED_MARKER)
    summary["unlisted_slash_dispatch"]["unlisted_body_ran"] = bool(
        dispatch.get("marker_returned"))
    summary["unlisted_slash_dispatch"]["note"] = (
        "True means /name dispatch ran an unlisted skill, so the skills "
        "allowlist is not an isolation boundary.")


if __name__ == "__main__":
    main()
