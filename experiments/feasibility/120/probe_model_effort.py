"""Probe Codex model listing, effort selection, and setting rejection.

No model turns. No credential needed. Tests:
- model/list returns supported models with reasoning-effort metadata.
- Supported effort values are accepted by thread/start.
- Unsupported effort values are explicitly rejected.
- Model not in the list is rejected.
"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shared import construct_env, hash_personal_roots, initialize
from _shared import list_models, personal_roots, start_app_server, start_thread
from _shared import stop_app_server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", type=Path, required=True, help="path to codex.exe")
    args = parser.parse_args()
    codex = args.codex.resolve(strict=True)
    state = Path(__file__).resolve().parent / "_scratch_120_model"
    state.mkdir(parents=True, exist_ok=True)
    private_home = state / "home"; codex_home = state / "codex-home"
    project = state / "project"
    for d in [private_home, codex_home, project]:
        d.mkdir(parents=True, exist_ok=True)
    env = construct_env(private_home, codex_home, state, codex.parent)
    before = hash_personal_roots()
    process, messages, error_log = start_app_server(codex, project, env)
    summary = {"model_calls": 0, "runner_version": "codex-cli-tested"}
    try:
        ok, init_resp = initialize(process, messages)
        summary["initialized"] = ok
        if not ok:
            summary["initialize_error"] = init_resp.get("error", {}).get("code")
            return print(json.dumps(summary, indent=2))

        models_result, models = list_models(process, messages)
        summary["model_list_ok"] = "result" in models_result
        summary["model_count"] = len(models)
        model_map = {}
        for m in models:
            mid = m.get("id") or m.get("model", "unknown")
            supported = []
            raw = m.get("supportedReasoningEfforts", [])
            for e in raw:
                if isinstance(e, dict):
                    supported.append(e.get("reasoningEffort", str(e)))
                else:
                    supported.append(e)
            model_map[mid] = {
                "is_default": m.get("isDefault", False),
                "efforts": supported,
                "max_input": m.get("maxInputTokens"),
                "max_output": m.get("maxOutputTokens"),
            }
        summary["models"] = model_map

        # Test: start a thread with a supported effort for the default model.
        default = next((m for m in models if m.get("isDefault")), None)
        if not default and models:
            default = models[0]
        if default:
            default_id = default.get("id") or default.get("model")
            efforts = default.get("supportedReasoningEfforts", [])
            effort_values = [e.get("reasoningEffort", e) if isinstance(e, dict) else e for e in efforts]
            if "low" in effort_values:
                test_effort = "low"
            elif effort_values:
                test_effort = effort_values[0]
            else:
                test_effort = None

            # supported effort
            if test_effort:
                resp = start_thread(process, messages, default_id, project, effort=test_effort)
                summary["supported_effort_accepted"] = "result" in resp
                summary["supported_effort"] = test_effort
                if "result" in resp:
                    thread_id = resp["result"].get("thread", {}).get("id")
                    summary["thread_created"] = bool(thread_id)

            # unsupported effort (use a value known not to exist)
            unsupported = "superultra"
            resp_bad = start_thread(process, messages, default_id, project, effort=unsupported,
                                    timeout=15)
            summary["unsupported_effort_rejected"] = "error" in resp_bad
            summary["unsupported_effort_error"] = resp_bad.get("error", {}).get("code",
                "missing") if "error" in resp_bad else "accepted-unexpected"
            summary["unsupported_effort_value"] = unsupported

        # Rejection of a model not in the list
        bogus = "nonexistent-model-120"
        resp_bogus = start_thread(process, messages, bogus, project, effort="low", timeout=15)
        summary["unknown_model_rejected"] = "error" in resp_bogus
        summary["unknown_model_error"] = resp_bogus.get("error", {}).get("code",
            "missing") if "error" in resp_bogus else "accepted-unexpected"

        print(json.dumps(summary, indent=2))
    finally:
        stderr = stop_app_server(process, error_log, state)
        after = hash_personal_roots()
        personal = dict(
            ("_".join(r.parts[-2:]) if len(r.parts) > 1 else r.name,
             a == b) for r, a, b in zip(personal_roots(), before, after))
        print(json.dumps({"stderr_signals": stderr, "personal_roots_unchanged": personal}, indent=2))


if __name__ == "__main__":
    main()
