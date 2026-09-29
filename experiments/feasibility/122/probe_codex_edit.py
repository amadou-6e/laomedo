"""Bounded Codex Skill Draft edit probe for specs issue #122.

The private Codex profile is reused from #120. Only disposable #122 workspaces
and a distinct #122 turn ledger are created here. No credential is copied.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "120"))
from _shared import (AppServer, RequestTimeout, codex_version, compare_personal_roots,
                     construct_env, credential_gate, hash_personal_roots,
                     model_efforts, read_turn_context, select_supported_pair,
                     validate_pair)
from probe_draft_guards import (BASE_SKILL, fixed_case_evaluation,
                                inventory, patch_for, policy_ref, restore,
                                snapshot, structural_validation, tree_hash)
from inspect_private_turn_policy import inspect_turn_policy


def reserve_turn(state: Path, limit: int = 6) -> int:
    """An abandoned reservation counts. A concurrent process fails closed."""
    ledger = state / "turn-budget-122.json"
    lock = state / "turn-budget-122.lock"
    descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.close(descriptor)
        attempts = 0
        if ledger.exists():
            record = json.loads(ledger.read_text(encoding="utf-8"))
            attempts = record["attempted_turns"]
            if not isinstance(attempts, int) or attempts < 0:
                raise ValueError("invalid_turn_ledger")
        if attempts >= limit:
            raise ValueError("issue_122_turn_cap_reached")
        attempts += 1
        pending = state / "turn-budget-122.pending"
        pending.write_text(json.dumps({"attempted_turns": attempts}) + "\n",
                           encoding="utf-8")
        os.replace(pending, ledger)
        return attempts
    finally:
        lock.unlink(missing_ok=True)


def event_summary(server: AppServer, since: int) -> dict:
    events = server.events[since:]
    counts = {}
    item_types = {}
    usage = []
    for event in events:
        method = event.get("method")
        if not method:
            continue
        counts[method] = counts.get(method, 0) + 1
        if method in ("item/started", "item/completed"):
            item = event.get("params", {}).get("item") or {}
            kind = item.get("type")
            if isinstance(kind, str):
                item_types[kind] = item_types.get(kind, 0) + 1
        if method == "thread/tokenUsage/updated":
            info = event.get("params", {}).get("tokenUsage") or {}
            if isinstance(info, dict):
                usage.append({key: value for key, value in info.items()
                              if key in ("last", "total") and isinstance(value, dict)})
    return {"method_counts": counts, "item_type_counts": item_types,
            "token_usage_updates": usage[-2:]}


def await_turn(server: AppServer, turn_id: str, since: int,
               timeout: float = 120) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for event in server.events[since:]:
            if event.get("method") != "turn/completed":
                continue
            turn = event.get("params", {}).get("turn") or {}
            if turn.get("id") == turn_id:
                return turn.get("status") or "unknown"
        server.drain(0.5)
    return "timeout"


def run_turn(server: AppServer, thread_id: str, model: str, effort: str,
             prompt: str, summary: dict, label: str, codex_home: Path,
             thread_path: str, project: Path) -> dict:
    count = reserve_turn(server.state)
    start = len(server.events)
    result = {"attempted_turn_number": count, "status": "submitted"}
    try:
        response = server.send("turn/start", {
            "threadId": thread_id, "model": model, "effort": effort,
            "cwd": str(project),
            "sandboxPolicy": {"type": "workspaceWrite",
                              "writableRoots": [str(project)],
                              "networkAccess": False},
            "input": [{"type": "text", "text": prompt}],
        }, timeout=30)
        if "result" not in response:
            result["status"] = "dispatch_rejected"
            result["error_present"] = "error" in response
            return result
        turn_id = response.get("result", {}).get("turn", {}).get("id")
        result["turn_id"] = turn_id
        result["status"] = await_turn(server, turn_id, start)
        result["effective_context"] = read_turn_context(
            codex_home, thread_path, turn_id)
        result["recorded_turn_policy"] = inspect_turn_policy(codex_home, turn_id)
    except RequestTimeout:
        result["status"] = "timeout"
    except Exception as exc:
        result["status"] = "error"
        result["error_class"] = type(exc).__name__
    finally:
        result["events"] = event_summary(server, start)
        summary[label] = result
    return result


def validate_draft(canonical: Path, draft: Path,
                   base_hash: str, current_revision: str = "1") -> dict:
    base = inventory(canonical)
    violations = []
    try:
        proposed = inventory(draft)
    except ValueError as exc:
        proposed = {}
        violations.append(str(exc))
    violations += structural_validation(base, proposed)
    if tree_hash(base) != base_hash:
        violations.append("canonical_changed")
    if current_revision != "1":
        violations.append("base_revision_conflict")
    changed = sorted(key for key in base.keys() | proposed.keys()
                     if base.get(key) != proposed.get(key))
    if not changed:
        violations.append("no_change")
    return {"base_hash": base_hash,
            "draft_hash": tree_hash(proposed) if proposed else None,
            "changed_paths": changed, "patch": patch_for(base, proposed)
            if proposed else None, "violations": sorted(set(violations)),
            "base_evaluation": fixed_case_evaluation(base),
            "draft_evaluation": fixed_case_evaluation(proposed)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--profile-dir", type=Path, required=True,
                        help="existing #120 private profile root; no auth copy")
    parser.add_argument("--state-dir", type=Path, required=True,
                        help="existing separate empty #122 private root outside Git")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    summary = {"issue": 122, "run_id": str(uuid4()),
               "policy_ref": policy_ref(), "model_calls": 0,
               "credential_mode": "chatgpt_handoff",
               "enforcement_scope": "Codex sandbox requested; post-edit validation verified separately"}
    try:
        if args.profile_dir.is_symlink() or args.state_dir.is_symlink():
            raise ValueError("private_root_symlink")
        codex = args.codex.resolve(strict=True)
        profile = args.profile_dir.resolve(strict=True)
        state = args.state_dir.resolve(strict=True)
        if not state.is_dir() or not profile.is_dir():
            raise ValueError("private_state_missing")
        from _shared import inside_git_tree
        if (inside_git_tree(state) or inside_git_tree(profile)
                or state != profile / "issue-122"):
            raise ValueError("private_roots_invalid")
        if (state / "codex-home").exists():
            raise ValueError("state_must_not_have_credential_copy")
        codex_home = profile / "codex-home"
        private_home = state / "home"
        run_dir = state / "runs" / summary["run_id"]
        project = run_dir / "draft-workspace"
        private_home.mkdir(exist_ok=True)
        project.mkdir(parents=True)
        env = construct_env(private_home, codex_home, state, codex.parent)
        gate = credential_gate(codex, project, env, codex_home, state)
        summary["credential_gate"] = gate
        summary["version"] = codex_version(codex, env)
        if not gate.get("permitted"):
            summary["blocked"] = "credential_gate"
            return
        server = AppServer(codex, project, env, state)
        try:
            ok, _ = server.initialize()
            if not ok:
                summary["blocked"] = "app_server_initialize"
                return
            listing = server.send("model/list", {})
            model, effort, capabilities = select_supported_pair(
                listing, "low", preferred_model="gpt-6-luna")
            if not validate_pair(capabilities, model, effort)["accepted"]:
                summary["blocked"] = "unsupported_model_effort"
                return
            summary["requested_model"] = model
            summary["requested_effort"] = effort
            if args.run:
                canary = project / "sandbox-probe.txt"
                checked = server.send("command/exec", {
                    "command": [str(Path(env["SystemRoot"]) / "System32" / "cmd.exe"),
                                "/c", "echo fixture > sandbox-probe.txt"],
                    "cwd": str(project),
                    "sandboxPolicy": {"type": "workspaceWrite",
                                      "writableRoots": [str(project)],
                                      "networkAccess": False},
                    "timeoutMs": 10000,
                }, timeout=20)
                summary["write_canary"] = {
                    "response_ok": "result" in checked,
                    "exit_code": (checked.get("result") or {}).get("exitCode"),
                    "file_written": canary.is_file() and
                    canary.read_text(encoding="utf-8").strip() == "fixture",
                }
                canary.unlink(missing_ok=True)
                if not summary["write_canary"]["file_written"]:
                    summary["blocked"] = "workspace_write_canary_failed"
                    return
        finally:
            summary["preflight_server_status"] = server.close()
        if not args.run:
            summary["preflight_only"] = True
            return
        canonical = run_dir / "canonical-skill"
        canonical.mkdir()
        (canonical / "SKILL.md").write_text(BASE_SKILL, encoding="utf-8")
        shutil.copy2(canonical / "SKILL.md", project / "SKILL.md")
        base_hash = tree_hash(inventory(canonical))
        summary["base_ref"] = {"revision_id": "1", "tree_hash": base_hash}
        before_personal = hash_personal_roots()
        server = AppServer(codex, project, env, state)
        try:
            ok, _ = server.initialize()
            if not ok:
                summary["blocked"] = "app_server_initialize_for_run"
                return
            started = server.send("thread/start", {
                "model": model, "cwd": str(project),
                "approvalPolicy": "never", "sandbox": "workspace-write",
            }, timeout=30)
            if "result" not in started:
                summary["blocked"] = "thread_start_rejected"
                return
            result = started["result"]
            thread_id = result["thread"]["id"]
            thread_path = result["thread"].get("path")
            summary["native_thread_id"] = thread_id
            summary["effective_sandbox"] = result.get("sandbox")
            summary["effective_approval_policy"] = result.get("approvalPolicy")
            summary["thread_sandbox_mismatch"] = (
                (summary["effective_sandbox"] or {}).get("type") != "workspaceWrite")
            first = run_turn(
                server, thread_id, model, effort,
                "Edit only SKILL.md in the current directory. Keep the YAML "
                "frontmatter and the amber rule unchanged. Append one short "
                "example line: Example: answer amber for the fixed case. "
                "Do not edit any other file.", summary, "allowed_edit",
                codex_home, thread_path, project)
        finally:
            summary["server_after_first"] = server.close()
        summary["model_calls"] = 1
        summary["after_first"] = validate_draft(canonical, project, base_hash)
        if first["status"] != "completed" or summary["after_first"]["violations"]:
            summary["resume_skipped"] = "first_edit_not_valid"
            return
        frozen = run_dir / "snapshots" / thread_id
        frozen.parent.mkdir(exist_ok=True)
        post_run_hash = snapshot(project, frozen)
        (project / "drift.txt").write_text("synthetic drift\n", encoding="utf-8")
        before_missing = tree_hash(inventory(project))
        try:
            restore(run_dir / "snapshots" / "missing", project, post_run_hash)
            summary["missing_snapshot_refused"] = False
        except ValueError:
            summary["missing_snapshot_refused"] = (
                tree_hash(inventory(project)) == before_missing)
        if not summary["missing_snapshot_refused"]:
            summary["resume_skipped"] = "missing_snapshot_accepted"
            return
        summary["restored_post_run_hash_matches"] = (
            restore(frozen, project, post_run_hash) == post_run_hash)
        if not summary["restored_post_run_hash_matches"]:
            summary["resume_skipped"] = "snapshot_restore_mismatch"
            return
        server = AppServer(codex, project, env, state)
        try:
            ok, _ = server.initialize()
            if not ok:
                summary["resume_skipped"] = "app_server_initialize_failed"
                return
            resumed = server.send("thread/resume", {"threadId": thread_id,
                                                     "cwd": str(project)}, timeout=30)
            if "result" not in resumed:
                summary["resume_skipped"] = "native_resume_rejected"
                return
            summary["resume_same_thread"] = (
                resumed["result"]["thread"]["id"] == thread_id)
            if not summary["resume_same_thread"]:
                summary["resume_skipped"] = "native_thread_changed"
                return
            second = run_turn(
                server, thread_id, model, effort,
                "Edit only SKILL.md in this current directory. Preserve its "
                "existing post-run example line. Add a second example line: "
                "Example: keep amber lowercase. Do not edit any other file.",
                summary, "resumed_edit", codex_home, thread_path, project)
        finally:
            summary["server_after_resume"] = server.close()
        summary["model_calls"] = 2
        summary["after_resume"] = validate_draft(canonical, project, base_hash)
        summary["resumed_edit_sees_post_run_file"] = (
            "Example: answer amber for the fixed case." in
            (project / "SKILL.md").read_text(encoding="utf-8", errors="replace"))
        summary["promotion_eligible"] = (
            second["status"] == "completed" and
            not summary["after_resume"]["violations"] and
            summary["resumed_edit_sees_post_run_file"])
    except Exception as exc:
        summary["blocked"] = type(exc).__name__
    finally:
        if "before_personal" in locals():
            summary["personal_roots_unchanged"] = compare_personal_roots(
                before_personal, hash_personal_roots())
        summary["promotion_performed"] = False
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
