"""Probe Claude Agent SDK streaming, failure, cancellation, and resume.

Credential required: the credential gate must pass before any model call.
Tests:
- Streamed messages contain a tool call (ToolUseBlock) and its matching result
  (ToolResultBlock with the same tool_use_id).
- Failure produces an explicit ResultMessage subtype or SDK error.
- Cancellation via client.interrupt() ends with terminal_reason aborted_*.
- A session ID captured from run 1 resumes in a fresh CLI process (each
  query() spawns a new process, which is the runner restart) and the init
  message reports the same session ID.
- Resuming an unknown session id fails explicitly.
- The workspace is fingerprinted before and after; the probe records that the
  SDK persists conversation only, so restoring the last post-run workspace
  snapshot is the Laomedo runner's responsibility.

Every credentialed call is bounded by max_turns and max_budget_usd.
"""

import asyncio
import json
import os
from pathlib import Path
import sys
import time

PROJECT_SKILL = "fixture-121-stream"


async def collect_query(prompt, options, summary, label, timeout_s=120):
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
    collected = collect_events(messages)
    summary[label] = {**outcome, **collected}
    return summary[label]


async def _query(prompt, options):
    from claude_agent_sdk import query
    async for message in query(prompt=prompt, options=options):
        yield message


async def run_interrupt(state, private_home, config_dir, summary):
    """Start a long turn, interrupt it, and drain to its ResultMessage."""
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage
    from claude_agent_sdk._errors import CLIConnectionError, CLINotFoundError
    from _shared import options_env, collect_events, count_attempted_turn

    options = ClaudeAgentOptions(
        cwd=str(state),
        env=options_env(private_home, config_dir),
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
        outcome["outcome"] = "cli_unavailable"
        outcome["error"] = type(exc).__name__
        summary["cancellation"] = {**outcome}
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
                        help="private state dir outside any git tree")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _shared import (compare_personal_roots, credential_gate, fingerprint,
                          hash_personal_roots, options_env, resettable_dir,
                          runner_versions, write_skill)

    state, leftovers = resettable_dir(args.state_dir.resolve())
    private_home = state / "home"
    config_dir = state / "claude-config"
    project = state / "project"
    for directory in (private_home, config_dir, project):
        directory.mkdir(parents=True, exist_ok=True)
    (project / "notes.txt").write_text(
        "The launch code is LAOMEDO-121-READY.\n", encoding="utf-8")
    write_skill(project / ".claude" / "skills", PROJECT_SKILL,
                "Synthetic streaming fixture for issue 121.")

    summary = dict(runner_versions())
    summary["scratch_leftovers"] = leftovers
    gate = credential_gate(state, config_dir)
    summary["credential_gate"] = gate
    if not gate.get("permitted"):
        print(json.dumps(summary, indent=2))
        return

    before = hash_personal_roots()

    try:
        from claude_agent_sdk import ClaudeAgentOptions
        from _shared import options_env

        def make_options(resume=None):
            return ClaudeAgentOptions(
                cwd=str(project),
                env=options_env(private_home, config_dir),
                setting_sources=["project"],
                skills=[PROJECT_SKILL],
                max_turns=3,
                max_budget_usd=2.0,
                permission_mode="default",
                allowed_tools=["Read", "Glob", "Grep"],
                resume=resume,
            )

        # Run 1: streamed tool call and matching result.
        run1 = asyncio.run(collect_query(
            "Read the file notes.txt in the project directory, then reply with "
            "exactly the launch code it contains.",
            make_options(), summary, "run1_stream"))

        # Workspace snapshot before and after run 1.
        summary["workspace_hash_run1"] = fingerprint(project)
        session_id = ((run1.get("result") or {}).get("session_id")
                      or (run1.get("init") or {}).get("session_id"))
        summary["run1_session_id"] = session_id

        if session_id:
            # Run 2: resume in a fresh CLI process (a new query() process is
            # the runner restart). Record that conversation resumes but the
            # workspace is the caller's responsibility.
            run2 = asyncio.run(collect_query(
                "Without reading the file again, reply with the launch code "
                "you read earlier.",
                make_options(resume=session_id), summary, "run2_resume"))
            summary["run2_session_id"] = ((run2.get("result") or {}).get("session_id")
                                          or (run2.get("init") or {}).get("session_id"))
            summary["resume_same_session"] = (summary["run2_session_id"] == session_id)

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
        asyncio.run(run_interrupt(state, private_home, config_dir, summary))

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
                                       "any response")
        summary["personal_roots_unchanged"] = compare_personal_roots(
            before, hash_personal_roots())
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
