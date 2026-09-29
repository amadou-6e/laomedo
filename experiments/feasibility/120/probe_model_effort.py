"""Probe Codex model listing, effort selection, and setting rejection.

Unauthenticated by construction. No turn is submitted. This probes model/list
and tests the runner's own pre-dispatch validation. The app-server accepted
invalid values in a prior no-credential run, so provider rejection is not the
boundary. Effective per-turn effort needs a credentialed completed turn.
"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shared import (AppServer, RequestTimeout, codex_version, construct_env,
                      hash_personal_roots, compare_personal_roots,
                      resettable_dir, summarize_methods, validate_pair,
                      write_skill)


def thread_start_effective(server, model):
    """Start a thread and report exactly which effective fields the server
    returned rather than asserting field names.

    Per the SDK 0.157.1 schema, the effective model, reasoningEffort, sandbox,
    and approvalPolicy are top-level fields of the thread/start result; the
    thread object itself may not carry them. Both sets of keys are recorded so
    a different runner version cannot be misread.
    """
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
        "reported_model": result.get("model") or thread.get("model"),
        "reported_effort": result.get("reasoningEffort") or thread.get("reasoningEffort"),
        "reported_sandbox": result.get("sandbox") or thread.get("sandbox"),
        "reported_approval_policy": result.get("approvalPolicy"),
        "cli_version": thread.get("cliVersion"),
        "instruction_sources": result.get("instructionSources"),
    }, thread.get("id")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", type=Path, required=True)
    args = parser.parse_args()
    codex = args.codex.resolve(strict=True)
    state, leftovers = resettable_dir(
        Path(__file__).resolve().parent / "_scratch_120_model")
    private_home = state / "home"
    codex_home = state / "codex-home"
    project = state / "project"
    for directory in (private_home, codex_home, project):
        directory.mkdir(parents=True, exist_ok=True)
    write_skill(project / ".agents" / "skills", "fixture-120-model")
    env = construct_env(private_home, codex_home, state, codex.parent)
    before = hash_personal_roots()
    summary = {"version": codex_version(codex, env), "model_calls": 0}

    server = AppServer(codex, project, env, state)
    try:
        ok, info = server.initialize()
        summary["initialized"] = ok
        summary["server_platform"] = {k: info.get(k) for k in ("userAgent", "platformFamily", "platformOs")}
        if not ok:
            summary["initialize_error"] = info
            return

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
            return
        model = selected.get("id") or selected.get("model")
        summary["selected_model"] = model
        requested_effort = supported_by_model[model]["default_effort"]
        summary["supported_pair"] = {
            "requested_model": model,
            "requested_effort": requested_effort,
            "validation": validate_pair(supported_by_model, model, requested_effort),
            "effective_turn_effort": "unknown_without_completed_turn",
        }

        if summary["supported_pair"]["validation"]["accepted"]:
            effective, thread_id = thread_start_effective(server, model)
            summary["thread_start_effective"] = effective
            summary["thread_created"] = bool(thread_id)

        narrow = next((mid for mid, data in supported_by_model.items()
                       if union - set(data["efforts"])), None)
        summary["predispatch_checks"] = {
            "unknown_model": validate_pair(supported_by_model,
                                           "nonexistent-model-120", "low"),
            "invalid_effort": validate_pair(supported_by_model, model,
                                            "superultra"),
        }
        if narrow:
            unsupported = sorted(union - set(supported_by_model[narrow]["efforts"]))[0]
            summary["predispatch_checks"]["valid_but_unsupported"] = {
                "model": narrow, "effort": unsupported,
                **validate_pair(supported_by_model, narrow, unsupported),
            }
        else:
            summary["predispatch_checks"]["valid_but_unsupported"] = {
                "not_applicable": "no model has a narrower effort set"}

        summary["event_methods"] = summarize_methods(server)
    except RequestTimeout as exc:
        summary["fatal_timeout"] = str(exc)
    finally:
        stderr = server.close()
        summary["stderr_signals"] = stderr
        summary["personal_roots_unchanged"] = compare_personal_roots(
            before, hash_personal_roots())
        summary["scratch_leftovers"] = leftovers
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
