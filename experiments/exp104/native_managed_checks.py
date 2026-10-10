"""Falsifiable S12 observation checks; this module executes no live operation."""
import math
import re

IDENTITY = "exp104-native-managed-s12-20261010-a"
REPOSITORY = "ga84jog/laomedo-exp104-disposable-20261007"
BASELINE = "1f1a505f2fbd31993a7946924a9bec5a27bb15c1"


def validate(value):
    """Refuse incomplete evidence even when its declared result says passed."""
    if (value.get("identity") != IDENTITY or value.get("repository") != REPOSITORY or
            value.get("baseline") != BASELINE or type(value.get("model_turns")) is not int or
            value.get("model_turns") != 0 or
            not re.fullmatch(r"[0-9a-f]{40}", value.get("source_sha", ""))):
        raise ValueError("source_or_scope_mismatch")
    # Provider reads may add journal records; the four-write budget is not
    # a four-total-request claim. Retain the full journal separately.
    journal = value.get("provider_mutations", [])
    if [event.get("operation") for event in journal] != [
            "git_push", "pr_create", "git_push", "pr_create"]:
        raise ValueError("provider_attempt_budget_or_order")
    delivery = value.get("delivery", {})
    for side in ("a", "b"):
        item = delivery.get(side, {})
        branch = IDENTITY + "-" + side
        if (item.get("container_owned_alive") is not True or
                not re.fullmatch(r"[0-9a-f]{40}", item.get("commit", "")) or
                item.get("branch") != branch or item.get("base") != "main" or
                type(item.get("pr_number")) is not int or item["pr_number"] < 1 or
                item.get("marker") != "laomedo:" + IDENTITY + ":pr:" + side or
                item.get("readback_commit") != item["commit"] or
                item.get("readback_matches") is not True or
                item.get("commands_confirmed") is not True):
            raise ValueError("delivery_readback_mismatch")
    if delivery["a"]["pr_number"] == delivery["b"]["pr_number"]:
        raise ValueError("run_targets_not_disjoint")
    for index, side in ((0, "a"), (2, "b")):
        if (journal[index].get("branch") != delivery[side]["branch"] or
                journal[index].get("commit") != delivery[side]["commit"]):
            raise ValueError("provider_target_mismatch")
    loss = value.get("loss", {})
    times = [loss.get(key) for key in ("kill_completed", "revoked", "denied")]
    if (any(type(t) not in (int, float) or not math.isfinite(t) for t in times) or
            not 0 <= times[1] - times[0] <= 60 or times[2] < times[1]):
        raise ValueError("revocation_bound_unproven")
    if (loss.get("denial_error") != "grant_unavailable" or
            loss.get("denial_status") != 403 or
            type(loss.get("attempts_before_denial")) is not int or
            loss["attempts_before_denial"] < 3 or
            loss.get("attempts_after_denial") != loss["attempts_before_denial"] or
            loss.get("pr_unchanged") is not True or
            loss.get("b_grant_active") is not True or
            loss.get("b_create_after_denial") is not True):
        raise ValueError("post_loss_control_mismatch")
    tasks = value.get("tasks", {})
    for name in ("host-services", "bundle-verifier"):
        item = tasks.get(name, {})
        before, after = item.get("before", []), item.get("after", [])
        if (not before or before != after or
                any(type(pid) is not int or pid <= 0 for pid in before) or
                any(item.get(flag) is not True for flag in
                    ("limited", "interactive", "ignore_new", "ownership_matches"))):
            raise ValueError("managed_lifetime_unproven")
    if value.get("heartbeat_advanced") is not True:
        raise ValueError("service_heartbeat_missing")
    if (type(value.get("unexpected_secret_hits")) is not int or
            value.get("unexpected_secret_hits") != 0 or
            type(value.get("scanned_files")) is not int or value["scanned_files"] < 1):
        raise ValueError("credential_scan_unproven")
    cleanup = value.get("cleanup", {})
    if (set(cleanup) != {"a", "b", "stages", "tasks", "processes", "grants"} or
            any(flag is not True for flag in cleanup.values())):
        raise ValueError("cleanup_unverified")
    return True
