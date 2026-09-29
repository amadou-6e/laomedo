"""Probe Codex thread persistence across runner restarts.

No model turns. Tests:
- Thread resume after app-server restart when workspace snapshot is present.
- Resume fails when the last post-run workspace snapshot is missing.
- Session data survives app-server teardown and restart (thread/list).
"""

import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shared import (construct_env, fingerprint, hash_personal_roots, initialize,
                      list_models, personal_roots, request, start_app_server,
                      start_thread, start_turn, stop_app_server, write_skill)


def list_threads(process, messages, cwd):
    try:
        return request(process, messages, {
            "method": "thread/list", "id": 10,
            "params": {"cwd": str(cwd)},
        }, timeout=15)
    except Exception:
        return {"error": {"code": "unsupported_method"}}


def resume_via_thread_start(process, messages, model, cwd, thread_id,
                            existing_threads):
    """Attempt to resume a thread using thread/start with threadId or by
    listing and picking the matching thread."""
    params = {
        "model": model, "cwd": str(cwd),
        "approvalPolicy": "never",
        "config": {"model_reasoning_effort": "low"},
        "sandbox": "read-only",
    }
    if thread_id:
        params["threadId"] = thread_id
    return request(process, messages, {
        "method": "thread/start", "id": 4,
        "params": params,
    }, timeout=20)


def run_and_resume(codex, project, env, model, summary):
    """Start a thread, submit a turn, restart, and attempt resume."""
    # Run 1: create thread + one turn
    process, messages, error_log = start_app_server(codex, project, env)
    try:
        ok, _ = initialize(process, messages)
        if not ok:
            summary["run1_init_error"] = True
            return None
        thr = start_thread(process, messages, model, project, timeout=20)
        if "error" in thr:
            summary["run1_thread_error"] = thr["error"].get("code")
            return None
        thread_id = thr["result"]["thread"]["id"]
        summary["run1_thread_id"] = thread_id
        turn = start_turn(process, messages, thread_id,
            input_items=[{"type": "text", "text": "Initial turn for persistence test."}],
            timeout=20)
        summary["run1_turn_accepted"] = "result" in turn
        if "error" in turn:
            summary["run1_turn_error"] = turn["error"].get("code")
    finally:
        stop_app_server(process, error_log, Path(env["TEMP"]))

    # Restart and attempt resume
    process2, messages2, err2 = start_app_server(codex, project, env)
    try:
        ok2, _ = initialize(process2, messages2)
        summary["resume_init_ok"] = ok2
        if not ok2:
            return thread_id

        tl = list_threads(process2, messages2, project)
        summary["thread_list_supported"] = "result" in tl
        if "result" in tl:
            threads = tl.get("result", {}).get("threads", [])
            summary["thread_count"] = len(threads)
            summary["thread_still_listed"] = any(
                t.get("id") == thread_id for t in threads)

        resume = resume_via_thread_start(process2, messages2, model, project,
                                          thread_id, threads if "result" in tl else [])
        summary["resume_accepted"] = "result" in resume
        if "error" in resume:
            summary["resume_error_code"] = resume["error"].get("code")
            summary["resume_error_msg"] = resume.get("error", {}).get("message", "")

        if "result" in resume:
            resumed_id = resume["result"].get("thread", {}).get("id")
            summary["resumed_thread_id"] = resumed_id
            summary["same_thread_resumed"] = resumed_id == thread_id
            turn2 = start_turn(process2, messages2, resumed_id,
                input_items=[{"type": "text", "text": "Resumed turn."}], timeout=20)
            summary["resume_turn_accepted"] = "result" in turn2
    finally:
        stop_app_server(process2, err2, Path(env["TEMP"]))

    return thread_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", type=Path, required=True)
    args = parser.parse_args()
    codex = args.codex.resolve(strict=True)
    state = Path(__file__).resolve().parent / "_scratch_120_persist"
    state.mkdir(parents=True, exist_ok=True)
    private_home = state / "home"; codex_home = state / "codex-home"
    project = state / "project"
    for d in [private_home, codex_home, project]:
        d.mkdir(parents=True, exist_ok=True)

    write_skill(project / ".agents" / "skills", "fixture-120-persist")
    env = construct_env(private_home, codex_home, state, codex.parent)
    before = hash_personal_roots()
    summary = {"model_calls": 0}

    # Resolve model first
    process, messages, error_log = start_app_server(codex, project, env)
    try:
        ok, _ = initialize(process, messages)
        if not ok:
            summary["init_error"] = True
            return print(json.dumps(summary, indent=2))
        _mr, models = list_models(process, messages)
        default = next((m for m in models if m.get("isDefault")), None)
        if not default and models:
            default = models[0]
        model = default.get("id") or default.get("model")
        summary["selected_model"] = model
    finally:
        stop_app_server(process, error_log, state)

    # Primary test: run, restart, resume
    thread_id = run_and_resume(codex, project, env, model, summary)
    summary["thread_created"] = bool(thread_id)

    # Test: resume with missing workspace snapshot
    if thread_id:
        project_backup = state / "project.backup"
        if project.exists():
            shutil.copytree(str(project), str(project_backup))
            shutil.rmtree(str(project))
        project_missing = state / "project"
        project_missing.mkdir(parents=True, exist_ok=True)
        write_skill(project_missing / ".agents" / "skills", "fixture-120-persist")
        summary["workspace_removed_for_test"] = True

        process3, messages3, err3 = start_app_server(codex, project_missing, env)
        try:
            ok3, _ = initialize(process3, messages3)
            resume_missing = resume_via_thread_start(process3, messages3, model,
                                                      project_missing, thread_id, [])
            summary["missing_ws_resume_accepted"] = "result" in resume_missing
            if "error" in resume_missing:
                summary["missing_ws_resume_error_code"] = resume_missing["error"].get("code")
                summary["missing_ws_resume_error_msg"] = resume_missing.get("error", {}).get("message", "")
        finally:
            stop_app_server(process3, err3, state)

        # Restore
        if project_backup.exists():
            if project_missing.exists():
                shutil.rmtree(str(project_missing))
            shutil.move(str(project_backup), str(project))

    after = hash_personal_roots()
    summary["personal_roots_unchanged"] = dict(
        ("_".join(r.parts[-2:]) if len(r.parts) > 1 else r.name,
         a == b) for r, a, b in zip(personal_roots(), before, after))

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
