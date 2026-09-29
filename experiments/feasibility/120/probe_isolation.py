"""Probe Codex skill and session isolation in a private runner.

No model turns. Verifies:
- Synthetic fixture skills are discovered in the private project/runner.
- No skills from the user's personal Codex profile or home are loaded.
- Starting a thread and turn (read-only, no model call) does not modify
  personal session or skill directories.
"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shared import (construct_env, hash_personal_roots, initialize,
                      list_skills, list_models, personal_roots, start_app_server,
                      start_thread, start_turn, stop_app_server, write_skill)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", type=Path, required=True)
    args = parser.parse_args()
    codex = args.codex.resolve(strict=True)
    state = Path(__file__).resolve().parent / "_scratch_120_iso"
    state.mkdir(parents=True, exist_ok=True)
    private_home = state / "home"; codex_home = state / "codex-home"
    project = state / "project"
    for d in [private_home, codex_home, project]:
        d.mkdir(parents=True, exist_ok=True)

    write_skill(project / ".agents" / "skills", "fixture-120")

    env = construct_env(private_home, codex_home, state, codex.parent)
    before = hash_personal_roots()
    process, messages, error_log = start_app_server(codex, project, env)
    summary = {"model_calls": 0}
    try:
        ok, init_resp = initialize(process, messages)
        summary["initialized"] = ok
        if not ok:
            summary["initialize_error"] = init_resp.get("error", {}).get("code")
            return print(json.dumps(summary, indent=2))

        skills = list_skills(process, messages, project)
        names = {s.get("name") for s in skills}
        summary["fixture_discovered"] = "fixture-120" in names
        state_resolved = state.resolve()
        real_home = Path.home().resolve()
        summary["skills_inside_private_state"] = sum(
            1 for s in skills if Path(s.get("path", "C:/missing")).resolve().is_relative_to(state_resolved))
        summary["skills_under_real_home"] = sum(
            1 for s in skills if Path(s.get("path", "C:/missing")).resolve().is_relative_to(real_home))
        summary["other_skill_count"] = len(names - {"fixture-120"})
        summary["other_skill_names"] = sorted(names - {"fixture-120"})

        models_result, models = list_models(process, messages)
        summary["model_list_ok"] = "result" in models_result
        model = None
        for m in models:
            mid = m.get("id") or m.get("model")
            if m.get("isDefault") or mid == "gpt-6-luna":
                model = mid
                break
        if not model and models:
            model = models[0].get("id") or models[0].get("model")
        if model:
            thr = start_thread(process, messages, model, project, timeout=20)
            if "result" in thr:
                thread_id = thr["result"].get("thread", {}).get("id")
                summary["thread_started"] = bool(thread_id)
                if thread_id:
                    turn_resp = start_turn(process, messages, thread_id,
                        input_items=[{"type": "text", "text": "No-op."}], timeout=20)
                    summary["turn_started"] = "result" in turn_resp
                    summary["turn_start_error"] = turn_resp.get("error", {}).get("code",
                        "missing") if "error" in turn_resp else None
            else:
                summary["thread_start_error"] = thr.get("error", {}).get("code")
        print(json.dumps(summary, indent=2))
    finally:
        stderr = stop_app_server(process, error_log, state)
        after = hash_personal_roots()
        summary_post = dict(
            ("_".join(r.parts[-2:]) if len(r.parts) > 1 else r.name,
             a == b) for r, a, b in zip(personal_roots(), before, after))
        print(json.dumps({"stderr_signals": stderr, "personal_roots_unchanged": summary_post}, indent=2))


if __name__ == "__main__":
    main()
