"""Pure acceptance and locked owner-authorized ledger extension for EXP-93."""
import json
import math
import os
from pathlib import Path
from uuid import uuid4

IDENTITY = "exp93-real-stage-s1-20261011-a"
TASK = "Run exactly one shell command: sh -c 'sleep 60; printf TOO-LATE > crash-marker.txt'. Do not run any other commands, use GitHub, inspect credentials, or modify any other files. This is a disposable crash-cleanup test."


def save(path, value):
    pending = path.with_name(path.name + ".pending")
    with pending.open("w", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(value, sort_keys=True, indent=2) + "\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(pending, path)


def reserve(path, state):
    """Keep the previous twelve entries; count the fresh attempt before dispatch."""
    path = Path(path)
    lock = path.with_suffix(".lock")
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if value.get("cap") != 12 or len(value.get("attempts", [])) != 12:
            raise ValueError("unexpected_prior_budget")
        if any(row.get("case_kind") == IDENTITY for row in value["attempts"]):
            raise ValueError("identity_already_consumed")
        entry = uuid4().hex
        value["cap"] = 16
        value["authorization_extension"] = {"date": "2026-10-11", "additional_turns": 4,
            "source": "owner explicitly requested four more model turns"}
        value["attempts"].append({"id": entry, "case_kind": IDENTITY,
            "state_dir": str(state), "result": "reserved_unknown"})
        save(path, value)
        return entry
    finally:
        lock.unlink()


def validate(value):
    if value.get("identity") != IDENTITY:
        raise ValueError("identity_mismatch")
    if value.get("boundary_observed") is not True:
        raise ValueError("native_boundary_missing")
    loss = value.get("loss", {})
    times = [loss.get(k) for k in ("command_started", "kill_completed", "revoked", "denied")]
    if any(type(t) not in (int, float) or not math.isfinite(t) for t in times):
        raise ValueError("timing_missing")
    if not times[0] <= times[1] <= times[2] <= times[3] or times[2]-times[1] > 60:
        raise ValueError("revocation_bound_failed")
    if (loss.get("denial_status") != 403 or loss.get("denial_error") != "grant_unavailable"
            or loss.get("attempts_before_denial") != loss.get("attempts_after_denial")):
        raise ValueError("write_refusal_not_proven")
    if (loss.get("a_container_absent") is not True or loss.get("b_owned_alive") is not True
            or loss.get("b_read_status") != 200 or loss.get("b_read_count") != 1):
        raise ValueError("ownership_or_continuity_failed")
    if value.get("provider_writes") != 0 or value.get("local_turns") != 1:
        raise ValueError("unexpected_effect_or_budget")
    if value.get("restart_status") != "interrupted" or value.get("restart_identity_retained") is not True:
        raise ValueError("restart_accounting_unproven")
    if value.get("shared_used") != 13 or value.get("shared_cap") != 16:
        raise ValueError("shared_budget_mismatch")
    if value.get("sentinel_checked_after") is None or value["sentinel_checked_after"] < 61:
        raise ValueError("sentinel_checked_too_early")
    if value.get("sentinel_present") is not False:
        raise ValueError("late_effect_seen")
    if not value.get("cleanup") or not all(v is True for v in value["cleanup"].values()):
        raise ValueError("cleanup_unverified")


def finalize(path, entry, result):
    lock = path.with_suffix(".lock")
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        value = json.loads(path.read_bytes())
        rows = [r for r in value["attempts"] if r.get("id") == entry and r.get("case_kind") == IDENTITY]
        if value.get("cap") != 16 or len(rows) != 1:
            raise ValueError("reserved_entry_missing")
        rows[0]["result"] = result
        save(path, value)
    finally:
        lock.unlink()


def identities(root, side):
    if side not in ("a", "b"):
        raise ValueError("invalid_side")
    branch = IDENTITY + "-" + side
    value = {"branch": branch, "invocation_id": IDENTITY + "-invocation-" + side}
    records = [json.loads(p.read_bytes()) for p in (root / "runner/runs").glob("*/record.json")]
    selected = [r for r in records if (r.get("github_scope") or {}).get("branch") == branch]
    if len(selected) > 1:
        raise ValueError("run_identity_conflict")
    if selected:
        record = selected[0]
        owner = record["container_ownership"]
        value.update(run_id=record["run_id"], name=owner["name"], token=owner["launch_token"],
                     grant_id=owner["grant_id"])
    return value
