"""Synthetic checker controls, never S12 campaign evidence or live execution."""
from copy import deepcopy
import pytest
from experiments.exp104.native_managed_checks import BASELINE, IDENTITY, REPOSITORY, validate


def observation():
    delivery = {side: {
        "container_owned_alive": True, "commit": commit, "branch": IDENTITY + "-" + side,
        "base": "main", "pr_number": number, "marker": "laomedo:" + IDENTITY + ":pr:" + side,
        "readback_commit": commit, "readback_matches": True, "commands_confirmed": True,
    } for side, commit, number in (("a", "a" * 40, 1), ("b", "b" * 40, 2))}
    return {"identity": IDENTITY, "repository": REPOSITORY, "baseline": BASELINE,
        "source_sha": "c" * 40, "model_turns": 0, "result": "passed",
        "delivery": delivery,
        "provider_attempts": [{"operation": op, "branch": delivery[side]["branch"],
            "commit": delivery[side]["commit"]} for side, op in
            (("a", "git_push"), ("a", "pr_create"), ("b", "git_push"), ("b", "pr_create"))],
        "loss": {"kill_completed": 100, "revoked": 105, "denied": 106,
            "denial_error": "grant_unavailable", "denial_status": 403,
            "attempts_before_denial": 3, "attempts_after_denial": 3,
            "pr_unchanged": True, "b_grant_active": True, "b_create_after_denial": True},
        "tasks": {name: {"before": [pid], "after": [pid], "limited": True,
            "interactive": True, "ignore_new": True, "ownership_matches": True}
            for name, pid in (("host-services", 10), ("bundle-verifier", 11))},
        "heartbeat_advanced": True, "unexpected_secret_hits": 0, "scanned_files": 10,
        "cleanup": {key: True for key in ("a", "b", "stages", "tasks", "processes", "grants")}}


def test_complete_synthetic_fixture_validates():
    assert validate(observation()) is True


@pytest.mark.parametrize("case", range(12))
def test_false_success_controls_are_rejected(case):
    value = deepcopy(observation())
    if case == 0: value["provider_attempts"].append({"operation": "pr_update"})
    elif case == 1: value["provider_attempts"].pop()
    elif case == 2: value["provider_attempts"][0]["branch"] = "wrong-run"
    elif case == 3: value["loss"]["revoked"] = 161
    elif case == 4: value["loss"]["denial_status"] = 200
    elif case == 5: value["loss"]["attempts_after_denial"] = 4
    elif case == 6: value["loss"]["b_grant_active"] = False
    elif case == 7: value["unexpected_secret_hits"] = 1
    elif case == 8: value["tasks"]["host-services"]["after"] = []
    elif case == 9: value["cleanup"]["stages"] = False
    elif case == 10: value["loss"]["revoked"] = float("nan")
    else: value["delivery"]["a"]["readback_commit"] = "0" * 40
    with pytest.raises(ValueError):
        validate(value)
