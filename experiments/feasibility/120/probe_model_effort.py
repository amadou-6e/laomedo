"""Probe Codex model listing, effort selection, and setting rejection.

No credential and no spend: this probe refuses to submit a model turn when a
credential is present unless --allow-spend is passed. It tests:
- model/list supported efforts and defaults.
- What the server reports as requested and effective on thread/start.
- Explicit rejection of an invalid effort string and of a valid-but-unsupported
  level (silent-downgrade check).
- Rejection of an unknown model id.

Caveat: with no credential, a rejected-setting check observes dispatch-time
validation only. It can show an explicit error; it cannot show that an accepted
turn would not have been silently downgraded.
"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shared import (AppServer, RequestTimeout, codex_version, construct_env,
                      credential_gate, hash_personal_roots, compare_personal_roots,
                      login_status, resettable_dir, summarize_methods, write_skill)


def thread_start_effective(server, model):
    """Start a thread and report exactly which effective fields the server
    returned, rather than asserting field names."""
    response = server.send("thread/start", {
        "model": model, "cwd": str(server.state), "approvalPolicy": "never",
        "sandbox": "read-only",
    }, timeout=30)
    if "result" not in response:
        return {"error": response.get("error")}, None
    result = response["result"]
    thread = result.get("thread", {})
    return {
        "result_keys": sorted(result.keys()),
        "thread_keys": sorted(thread.keys()),
        "reported_model": thread.get("model"),
        "reported_effort": thread.get("reasoningEffort") or thread.get("effort"),
        "instruction_sources": result.get("instructionSources"),
    }, thread.get("id")


def effort_dispatch(server, model, effort):
    """Start a fresh thread and submit a turn with the given effort.
    Classifies the immediate response as rejected or accepted."""
    fresh = server.send("thread/start", {
        "model": model, "cwd": str(server.state), "approvalPolicy": "never",
        "sandbox": "read-only",
    }, timeout=30)
    if "result" not in fresh:
        return {"outcome": "thread_start_failed", "error": fresh.get("error")}
    thread_id = fresh["result"]["thread"]["id"]
    response = server.send("turn/start", {
        "threadId": thread_id, "input": [{"type": "text", "text": "No-op."}],
        "model": model, "effort": effort,
    }, timeout=30)
    if "error" in response:
        return {"outcome": "rejected",
                "error": response["error"]}
    turn = response.get("result", {}).get("turn", {})
    return {"outcome": "accepted",
            "turn_keys": sorted(turn.keys()),
            "reported_effort": turn.get("reasoningEffort") or turn.get("effort")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--allow-spend", action="store_true",
                        help="permit turn/start dispatch tests with a credential")
    args = parser.parse_args()
    codex = args.codex.resolve(strict=True)
    state = resettable_dir(Path(__file__).resolve().parent / "_scratch_120_model")
    private_home = state / "home"
    codex_home = state / "codex-home"
    project = state / "project"
    for directory in (private_home, codex_home, project):
        directory.mkdir(parents=True, exist_ok=True)
    write_skill(project / ".agents" / "skills", "fixture-120-model")
    env = construct_env(private_home, codex_home, state, codex.parent)
    before = hash_personal_roots()
    summary = {"version": codex_version(codex, env), "model_calls_planned": 0}

    server = AppServer(codex, project, env, state)
    try:
        ok, info = server.initialize()
        summary["initialized"] = ok
        summary["server_platform"] = {k: info.get(k) for k in ("userAgent", "platformFamily", "platformOs")}
        if not ok:
            summary["initialize_error"] = info
            return print(json.dumps(summary, indent=2))

        listing = server.send("model/list", {"limit": 100})
        models = listing.get("result", {}).get("data", [])
        summary["model_list_ok"] = "result" in listing
        summary["model_count"] = len(models)
        supported_by_model = {}
        union = set()
        for model in models:
            mid = model.get("id") or model.get("model")
            levels = [e.get("reasoningEffort") if isinstance(e, dict) else e
                      for e in model.get("supportedReasoningEfforts", [])]
            supported_by_model[mid] = {
                "is_default": model.get("isDefault", False),
                "efforts": levels,
                "default_effort": model.get("defaultReasoningEffort"),
            }
            union.update(levels)
        summary["models"] = supported_by_model
        summary["effort_union"] = sorted(x for x in union if x)

        selected = next((m for m in models if m.get("isDefault")), None) or (models[0] if models else None)
        if not selected:
            summary["no_models"] = True
            return print(json.dumps(summary, indent=2))
        model = selected.get("id") or selected.get("model")
        summary["selected_model"] = model
        model_efforts = supported_by_model.get(model, {}).get("efforts", [])

        # Effective values reported by thread/start (no model call).
        effective, thread_id = thread_start_effective(server, model)
        summary["thread_start_effective"] = effective
        summary["thread_created"] = bool(thread_id)

        # Unknown model rejection (no model call).
        unknown = server.send("thread/start", {
            "model": "nonexistent-model-120", "cwd": str(project),
            "approvalPolicy": "never", "sandbox": "read-only",
        }, timeout=20)
        summary["unknown_model"] = {
            "outcome": "rejected" if "error" in unknown else "accepted",
            "error": unknown.get("error"),
        }

        # Effort dispatch checks.
        status = login_status(codex, project, env)
        summary["auth_mode"] = {k: status.get(k) for k in ("ok", "chatgpt", "api_key")}
        authenticated = bool(status.get("chatgpt") or status.get("api_key"))
        if authenticated and not args.allow_spend:
            summary["effort_checks"] = {
                "skipped": True,
                "reason": "credential_present_without_allow_spend",
            }
        else:
            valid_unsupported = sorted(union - set(model_efforts))
            checks = {}
            checks["invalid_string"] = {"effort": "superultra",
                                        "value_space": "not_a_valid_level"}
            if valid_unsupported:
                checks["valid_but_unsupported"] = {
                    "effort": valid_unsupported[0],
                    "value_space": "valid_level_absent_from_model",
                }
            else:
                checks["valid_but_unsupported"] = {
                    "not_applicable": "every valid level is supported by the selected model"}
            results = {}
            for name, case in checks.items():
                if "not_applicable" in case:
                    results[name] = case
                    continue
                try:
                    results[name] = {
                        **case,
                        **effort_dispatch(server, model, case["effort"]),
                    }
                except RequestTimeout as exc:
                    results[name] = {**case, "outcome": "timeout",
                                     "method": str(exc)}
            summary["effort_checks"] = results

        summary["event_methods"] = summarize_methods(server)
        print(json.dumps(summary, indent=2))
    finally:
        stderr = server.close()
        print(json.dumps({"stderr_signals": stderr}, indent=2))
        print(json.dumps({"personal_roots_unchanged":
                          compare_personal_roots(before, hash_personal_roots())}, indent=2))


if __name__ == "__main__":
    main()
