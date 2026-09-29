"""Probe Codex thread persistence across runner restarts.

Credential required: a thread is only persisted after a completed turn, so this
probe stops before any model call unless the private ChatGPT handoff or optional
dedicated API-key credential gate passes.

Tests:
- thread/resume reopens the same native thread id after an app-server restart.
- A resumed turn appends to the same thread.
- thread/list surfaces the thread after restart.
- Resuming an unknown thread id fails explicitly.
- Resume from a different cwd is recorded (Codex accepts or rejects it).

Scope limit: Codex has no concept of a Laomedo workspace snapshot. This probe
guards and restores one private post-run snapshot before native resume; a
production runner registry remains out of scope.
"""

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shared import (AppServer, RequestTimeout, codex_version,
                      compare_personal_roots, construct_env, credential_gate,
                      fingerprint, hash_personal_roots, read_turn_context,
                      reserve_model_turn, restore_workspace_snapshot,
                      select_supported_pair,
                      snapshot_workspace, summarize_methods, validate_pair,
                      write_skill)


def await_turn(server, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for message in server.events:
            if message.get("method") == "turn/completed":
                return message.get("params", {}).get("turn", {}).get("status")
        server.drain(0.5)
    return "timeout"


def count_attempted_turn(summary, state):
    """Count a turn/start immediately before sending it. The count is an upper
    bound on billable model calls: a submitted turn/start may still be rejected
    before generation, but every billable call must have been submitted."""
    summary["cumulative_attempted_turns"] = reserve_model_turn(state)
    summary["model_calls"] = summary.get("model_calls", 0) + 1


def create_and_run(server, model, project, summary, label):
    started = server.send("thread/start", {
        "model": model, "cwd": str(project), "approvalPolicy": "never",
        "sandbox": "read-only",
    }, timeout=30)
    if "result" not in started:
        summary[f"{label}_thread_error"] = started.get("error")
        return None
    result = started["result"]
    thread_id = result["thread"]["id"]
    summary[f"{label}_thread_id"] = thread_id
    thread_path = result["thread"].get("path")
    summary[f"{label}_cli_version"] = result["thread"].get("cliVersion")
    summary[f"{label}_instruction_source_count"] = len(result.get("instructionSources") or [])
    count_attempted_turn(summary, server.state)
    turn = server.send("turn/start", {
        "threadId": thread_id,
        "input": [{"type": "text", "text": "Reply with the single word ready."}],
        "model": model, "effort": "low",
    }, timeout=30)
    if "error" in turn:
        summary[f"{label}_turn_error"] = turn["error"]
        return thread_id
    turn_id = turn.get("result", {}).get("turn", {}).get("id")
    summary[f"{label}_turn_id"] = turn_id
    summary[f"{label}_turn_status"] = await_turn(server)
    summary[f"{label}_effective_context"] = read_turn_context(
        Path(server.state) / "codex-home", thread_path, turn_id)
    return thread_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path,
                        help="provisioned private state dir with codex-home/auth.json")
    parser.add_argument("--credential-mode", choices=("chatgpt_handoff", "api_key"),
                        default="chatgpt_handoff")
    parser.add_argument("--credential-ref", help="API-key secret-store reference, not a key")
    args = parser.parse_args()
    codex = args.codex.resolve(strict=True)
    if not args.state_dir:
        print(json.dumps({"blocked": "no_state_dir",
                          "detail": "pass --state-dir with provisioned private auth"}, indent=2))
        return
    state = args.state_dir.resolve(strict=True)
    if not state.is_dir():
        print(json.dumps({"blocked": "state_dir_missing"}, indent=2))
        return
    private_home = state / "home"
    codex_home = state / "codex-home"
    project = state / "project"
    for directory in (private_home, codex_home, project):
        directory.mkdir(parents=True, exist_ok=True)
    write_skill(project / ".agents" / "skills", "fixture-120-persist")
    env = construct_env(private_home, codex_home, state, codex.parent)

    summary = {"version": codex_version(codex, env)}
    gate = credential_gate(codex, project, env, codex_home, state,
                           args.credential_mode, args.credential_ref)
    summary["credential_gate"] = gate
    if not gate.get("permitted"):
        print(json.dumps(summary, indent=2))
        return

    before = hash_personal_roots()
    source_workspace_hash = fingerprint(project)
    summary["source_workspace_hash"] = source_workspace_hash
    thread_id = None
    model = None

    try:
        # Run 1: create a thread and complete a turn.
        server = AppServer(codex, project, env, state)
        summary["run1_private_event_log"] = server.event_log_path.name
        try:
            ok, _ = server.initialize()
            summary["run1_initialized"] = ok
            if ok:
                listing = server.send("model/list", {"limit": 100})
                model, effort, capabilities = select_supported_pair(
                    listing, preferred_model="gpt-6-luna")
                summary["requested_settings"] = {"model": model, "effort": effort}
                summary["pair_validation"] = validate_pair(capabilities, model, effort)
                thread_id = create_and_run(server, model, project, summary, "run1")
        except RequestTimeout as exc:
            summary["run1_fatal_timeout"] = str(exc)
        finally:
            summary["run1_stderr"] = server.close()
            summary["run1_event_methods"] = summarize_methods(server)

        if not thread_id or summary.get("run1_turn_status") != "completed":
            summary["resume_skipped"] = "first_turn_not_completed"
            return

        pre_restart = fingerprint(project)
        summary["read_only_workspace_unchanged"] = (
            pre_restart == source_workspace_hash)
        if not summary["read_only_workspace_unchanged"]:
            summary["resume_skipped"] = "read_only_workspace_changed"
            return
        summary["pre_restart_workspace_hash"] = pre_restart
        snapshot = state / "workspace-snapshots" / thread_id
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot_hash = snapshot_workspace(state, project, snapshot)
        summary["post_run_snapshot_hash"] = snapshot_hash
        # Simulate workspace drift between processes, then restore the exact
        # post-run files before asking Codex to resume.
        (project / "_probe_workspace_drift.txt").write_text("drift", encoding="utf-8")
        summary["workspace_drift_detected"] = fingerprint(project) != snapshot_hash
        summary["restored_workspace_hash"] = restore_workspace_snapshot(
            state, project, snapshot, snapshot_hash)
        summary["restored_workspace_matches_snapshot"] = (
            fingerprint(project) == snapshot_hash == pre_restart)
        if not summary["restored_workspace_matches_snapshot"]:
            summary["resume_skipped"] = "workspace_restore_mismatch"
            return
        try:
            restore_workspace_snapshot(state, project,
                                       state / "workspace-snapshots" / "missing",
                                       snapshot_hash)
        except FileNotFoundError:
            summary["missing_snapshot_rejected"] = True
        else:
            summary["missing_snapshot_rejected"] = False
            summary["resume_skipped"] = "missing_snapshot_was_accepted"
            return

        # Run 2: restart and resume the same thread.
        server = AppServer(codex, project, env, state)
        summary["run2_private_event_log"] = server.event_log_path.name
        try:
            ok, _ = server.initialize()
            summary["run2_initialized"] = ok
            if not ok:
                summary["resume_skipped"] = "restart_initialize_failed"
                return
            listed = server.send("thread/list", {"cwd": str(project)}, timeout=20)
            summary["thread_list_ok"] = "result" in listed
            if "result" in listed:
                payload = listed["result"]
                summary["thread_list_result_keys"] = sorted(payload.keys())
                threads = payload.get("data") or payload.get("threads") or []
                summary["thread_list_count"] = len(threads)
                summary["thread_found_after_restart"] = any(
                    (t.get("id") or t.get("threadId")) == thread_id for t in threads)

            resumed = server.send("thread/resume", {"threadId": thread_id}, timeout=30)
            summary["resume_ok"] = "result" in resumed
            if "error" in resumed:
                summary["resume_error"] = resumed["error"]
            else:
                result = resumed["result"]
                resumed_thread = result.get("thread", {})
                summary["resume_same_id"] = resumed_thread.get("id") == thread_id
                summary["resume_cli_version"] = resumed_thread.get("cliVersion")
                summary["resume_instruction_source_count"] = len(result.get("instructionSources") or [])
                if model:
                    count_attempted_turn(summary, state)
                    turn = server.send("turn/start", {
                        "threadId": thread_id,
                        "input": [{"type": "text", "text": "Reply with the single word resumed."}],
                        "model": model, "effort": "low",
                    }, timeout=30)
                    if "error" in turn:
                        summary["resume_turn_error"] = turn["error"]
                    else:
                        summary["resume_turn_id"] = turn.get("result", {}).get("turn", {}).get("id")
                        summary["resume_turn_status"] = await_turn(server)
                        summary["resume_effective_context"] = read_turn_context(
                            codex_home, resumed_thread.get("path"),
                            summary["resume_turn_id"])

            # Unknown thread id must fail explicitly.
            unknown = server.send("thread/resume", {"threadId": "thr_does_not_exist_120"}, timeout=20)
            summary["unknown_thread"] = {
                "outcome": "rejected" if "error" in unknown else "accepted",
                "error": unknown.get("error"),
            }
        except RequestTimeout as exc:
            summary["run2_fatal_timeout"] = str(exc)
        finally:
            summary["run2_stderr"] = server.close()
            summary["run2_event_methods"] = summarize_methods(server)

        # Run 3: resume from a different cwd (recorded, not asserted).
        other_cwd = state / "other-cwd"
        other_cwd.mkdir(parents=True, exist_ok=True)
        server = AppServer(codex, other_cwd, env, state)
        summary["run3_private_event_log"] = server.event_log_path.name
        try:
            ok, _ = server.initialize()
            summary["run3_initialized"] = ok
            moved = server.send("thread/resume", {"threadId": thread_id, "cwd": str(other_cwd)}, timeout=20)
            summary["resume_other_cwd"] = {
                "outcome": "accepted" if "result" in moved else "rejected",
                "error": moved.get("error"),
            }
        except RequestTimeout as exc:
            summary["run3_fatal_timeout"] = str(exc)
        finally:
            summary["run3_stderr"] = server.close()
            summary["run3_event_methods"] = summarize_methods(server)
    except Exception as exc:
        summary["fatal"] = type(exc).__name__
    finally:
        # One summary print on every path, including a crash mid-run.
        summary["model_calls_note"] = ("upper bound on billable model calls: a "
                                       "turn/start is counted when submitted, "
                                       "before any response")
        summary["personal_roots_unchanged"] = compare_personal_roots(
            before, hash_personal_roots())
        summary["note"] = ("The spike guards and restores a private post-run "
                           "snapshot; a production runner registry remains "
                           "out of scope (see 120.md).")
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
