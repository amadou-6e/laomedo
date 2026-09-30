"""Probe Codex skill, session, and instruction isolation in a private runner.

No credential and no model call: it calls initialize, skills/list, model/list,
and thread/start only. thread/start creates a local thread and returns
instructionSources; it does not start a turn or bill a model.

Tests:
- A synthetic fixture skill is discovered in the private project.
- No skill path resolves under the real user home.
- instructionSources do not include a file under the real user home
  (a personal AGENTS.md leak check).
- Personal skill/session roots are unchanged.
"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shared import (AppServer, codex_version, compare_personal_roots,
                      construct_env, hash_personal_roots, resettable_dir,
                      summarize_methods, write_skill)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", type=Path, required=True)
    args = parser.parse_args()
    codex = args.codex.resolve(strict=True)
    state, leftovers = resettable_dir(
        Path(__file__).resolve().parent / "_scratch_120_iso")
    private_home = state / "home"
    codex_home = state / "codex-home"
    project = state / "project"
    for directory in (private_home, codex_home, project):
        directory.mkdir(parents=True, exist_ok=True)
    write_skill(project / ".agents" / "skills", "fixture-120-iso")
    write_skill(private_home / ".agents" / "skills", "fixture-user-120-iso")

    env = construct_env(private_home, codex_home, state, codex.parent)
    before = hash_personal_roots()
    real_home = Path.home().resolve()
    summary = {"version": codex_version(codex, env), "model_calls": 0}

    server = AppServer(codex, project, env, state)
    try:
        ok, info = server.initialize()
        summary["initialized"] = ok
        summary["server_platform"] = {k: info.get(k) for k in ("userAgent", "platformFamily", "platformOs")}
        if not ok:
            summary["initialize_error"] = info
            return

        listing = server.send("skills/list", {
            "cwds": [str(project)], "forceReload": True})
        skills = listing.get("result", {}).get("data", [{}])[0].get("skills", [])
        names = {s.get("name") for s in skills}
        state_resolved = state.resolve()
        inside_state = 0
        under_real_home = 0
        outside_both = 0
        for skill in skills:
            path = Path(skill.get("path", "C:/missing")).resolve()
            if path.is_relative_to(state_resolved):
                inside_state += 1
            elif path.is_relative_to(real_home):
                under_real_home += 1
            else:
                outside_both += 1
        summary["fixture_discovered"] = "fixture-120-iso" in names
        summary["user_fixture_discovered"] = "fixture-user-120-iso" in names
        summary["skill_counts"] = {
            "total": len(skills),
            "inside_private_state": inside_state,
            "under_real_home": under_real_home,
            "outside_both": outside_both,
        }
        summary["other_skill_count"] = sum(
            bool(name and not name.startswith("fixture-")) for name in names)

        models = server.send("model/list", {"limit": 100})
        model_data = models.get("result", {}).get("data", [])
        summary["model_list_ok"] = "result" in models
        selected = next((m for m in model_data if m.get("isDefault")), None) or (model_data[0] if model_data else None)
        if selected:
            model = selected.get("id") or selected.get("model")
            summary["selected_model"] = model
            started = server.send("thread/start", {
                "model": model, "cwd": str(project), "approvalPolicy": "never",
                "sandbox": "read-only",
            }, timeout=30)
            if "result" in started:
                result = started["result"]
                thread = result.get("thread", {})
                summary["thread_created"] = True
                summary["thread_keys"] = sorted(thread.keys())
                summary["cli_version"] = thread.get("cliVersion")
                summary["effective_model"] = (result.get("model")
                                              or thread.get("model"))
                summary["effective_effort"] = (result.get("reasoningEffort")
                                               or thread.get("reasoningEffort"))
                sources = result.get("instructionSources") or []
                summary["instruction_source_count"] = len(sources)
                summary["instruction_source_under_real_home"] = sum(
                    1 for source in sources
                    if Path(source).resolve().is_relative_to(real_home))
                summary["instruction_sources_outside_private_state"] = sum(
                    1 for source in sources
                    if not Path(source).resolve().is_relative_to(state_resolved)
                    and not Path(source).resolve().is_relative_to(real_home))
            else:
                summary["thread_start_error"] = started.get("error")

        summary["event_methods"] = summarize_methods(server)
    except Exception as exc:
        summary["fatal"] = f"{type(exc).__name__}: {exc}"
    finally:
        stderr = server.close()
        summary["stderr_signals"] = stderr
        summary["scratch_leftovers"] = leftovers
        print(json.dumps(summary, indent=2))
        print(json.dumps({"personal_roots_unchanged":
                          compare_personal_roots(before, hash_personal_roots())}, indent=2))


if __name__ == "__main__":
    main()
