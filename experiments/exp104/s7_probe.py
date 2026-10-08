"""Single-use, no-model EXP-104 S7 runner-loss probe.

This module must be reviewed at an exact commit before ``--run`` is used.
It never retries a provider mutation after an uncertain result. The selected
GitHub token stays in the host process; Docker receives only a run capability.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib import error, request

from laomedo.container_lease import inspect_exact
from laomedo.host_token_connection import HostTokenConnection
from laomedo.lease_service import LeaseClient
from laomedo.local_runner import IMAGE, _docker_prefix
from laomedo.mediation_authority import RunGrantAuthority

from experiments.exp104.live_probe import (
    BASELINE, REPOSITORY, REPOSITORY_ID, _api, _base_git_environment,
    _call_count, _git, _kill_runner, _process, _stop, _wait,
)


IDENTITY = "exp104-s7-20261007-01"
CONNECTION_ID = IDENTITY + "-connection"
GENERATION = 1
BRANCHES = {side: IDENTITY + "-" + side for side in ("a", "b")}
MARKERS = {side: "laomedo:" + IDENTITY + ":pr:" + side for side in ("a", "b")}
RUNS = {side: IDENTITY + "-run-" + side for side in ("a", "b")}
LEASES = {side: IDENTITY + "-lease-" + side for side in ("a", "b")}
NAMES = {side: "laomedo-" + IDENTITY + "-" + side for side in ("a", "b")}


def _agent_environment() -> dict[str, str]:
    environment = _base_git_environment()
    environment.pop("GH_LAOMEDO", None)
    environment.pop("LAOMEDO_MEDIATED_GIT_TOKEN", None)
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    return environment


def _read_list(token: str, path: str) -> list[dict]:
    call = request.Request("https://api.github.com" + path, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "laomedo-exp104-s7/0.1",
    })
    with request.urlopen(call, timeout=15) as response:
        value = json.load(response)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise RuntimeError("github_list_invalid")
    return value


def _absent_ref(token: str, branch: str) -> None:
    try:
        _api(token, "/repos/" + REPOSITORY + "/git/ref/heads/" + branch)
    except error.HTTPError as failure:
        if failure.code == 404:
            return
        raise RuntimeError("branch_preflight_uncertain") from None
    raise RuntimeError("branch_already_exists")


def _remote_pr(token: str, number: int, side: str, *, title: str | None = None) -> dict:
    value = _api(token, f"/repos/{REPOSITORY}/pulls/{number}")
    head = value.get("head") or {}
    base = value.get("base") or {}
    if (head.get("ref") != BRANCHES[side] or
            (head.get("repo") or {}).get("full_name") != REPOSITORY or
            base.get("ref") != "main" or MARKERS[side] not in value.get("body", "") or
            (title is not None and value.get("title") != title)):
        raise RuntimeError("remote_pr_mismatch")
    return {"number": number, "head": head["ref"], "base": base["ref"],
            "title": value.get("title"), "marker_present": True}


def _preflight(token: str) -> None:
    repo = _api(token, "/repos/" + REPOSITORY)
    main = _api(token, "/repos/" + REPOSITORY + "/git/ref/heads/main")
    user = _api(token, "/user")
    if (repo.get("id") != REPOSITORY_ID or repo.get("default_branch") != "main" or
            repo.get("permissions", {}).get("push") is not True or
            main.get("object", {}).get("sha") != BASELINE or
            user.get("login") != "ga84jog"):
        raise RuntimeError("github_baseline_mismatch")
    for branch in BRANCHES.values():
        _absent_ref(token, branch)
    # The disposable repository is small; refuse an incomplete page rather
    # than mistaking an unseen marker for absence.
    pulls = _read_list(token, f"/repos/{REPOSITORY}/pulls?state=all&per_page=100")
    if len(pulls) == 100 or any(
            any(marker in str(pr.get(field, "")) for field in ("title", "body"))
            for pr in pulls for marker in MARKERS.values()):
        raise RuntimeError("pr_marker_preflight_uncertain")
    image = subprocess.run(["docker", "image", "inspect", IMAGE],
                           capture_output=True, timeout=20)
    if image.returncode:
        raise RuntimeError("pinned_image_unavailable")


def _prepare_commits(checkout: Path) -> dict[str, str]:
    if checkout.exists():
        raise RuntimeError("checkout_already_exists")
    _git("clone", "--quiet", "https://github.com/" + REPOSITORY + ".git",
         str(checkout))
    if _git("rev-parse", "HEAD", cwd=checkout) != BASELINE:
        raise RuntimeError("clone_baseline_mismatch")
    _git("config", "user.name", "Laomedo EXP-104", cwd=checkout)
    _git("config", "user.email", "exp104@example.invalid", cwd=checkout)
    commits = {}
    for side in ("a", "b"):
        _git("checkout", "--quiet", "--detach", BASELINE, cwd=checkout)
        marker = checkout / ("exp104-s7-" + side + ".txt")
        marker.write_text(MARKERS[side] + "\n", encoding="utf-8", newline="\n")
        _git("add", marker.name, cwd=checkout)
        _git("commit", "-qm", "EXP-104 S7 disposable " + side, cwd=checkout)
        commits[side] = _git("rev-parse", "HEAD", cwd=checkout)
    return commits


def _check_effect(status: int, response: dict, operation: str) -> dict:
    if status != 200 or response.get("state") != "confirmed" or not isinstance(
            response.get("result"), dict):
        raise RuntimeError(operation + "_not_confirmed_no_retry")
    return response["result"]


def _mediate(port: int, instance: str, capability: str, operation: str,
             payload: dict, effect_id: str) -> tuple[int, dict]:
    body = json.dumps({"repository": REPOSITORY, "operation": operation,
                       "payload": payload, "effect_id": effect_id}).encode()
    call = request.Request(f"http://127.0.0.1:{port}/v1/mediate", data=body,
                           method="POST", headers={
                               "Authorization": "Bearer " + capability,
                               "X-Laomedo-Mediator-Instance": instance,
                               "Content-Type": "application/json"})
    try:
        with request.urlopen(call, timeout=35) as response:
            return response.status, json.load(response)
    except error.HTTPError as failure:
        return failure.code, json.load(failure)


def _container_call(name: str, operation: str, payload: dict,
                    effect_id: str, forbidden: tuple[str, ...]) -> tuple[int, dict]:
    body = json.dumps({"repository": REPOSITORY, "operation": operation,
                       "payload": payload, "effect_id": effect_id})
    result = subprocess.run(["docker", "exec", "-i", name, "node",
                             "/run/laomedo/mediate.mjs"], input=body,
                            text=True, capture_output=True, timeout=35,
                            env=_agent_environment())
    if any(secret and secret in (result.stdout + result.stderr) for secret in forbidden):
        raise RuntimeError("secret_in_agent_response")
    if result.returncode not in (0, 1):
        raise RuntimeError("container_mediation_transport_unknown")
    try:
        response = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise RuntimeError("container_mediation_response_unknown") from None
    if not isinstance(response, dict):
        raise RuntimeError("container_mediation_response_unknown")
    return (200 if result.returncode == 0 else 403), response


def _agent_runner(state: Path, side: str, ready: Path) -> None:
    run_id, token, name = RUNS[side], LEASES[side], NAMES[side]
    lease = LeaseClient(state / "lease", run_id=run_id, name=name, token=token,
                        cancelled=threading.Event(), mediation_request={
                            "invocation_id": "invocation-" + run_id,
                            "repository": REPOSITORY, "branch": BRANCHES[side]})
    info = json.loads((state / "mediator" / "mediator.json").read_text(encoding="utf-8"))
    workspace = state / ("agent-" + side)
    for child in (workspace, workspace / "canonical", workspace / "store"):
        child.mkdir(parents=True, exist_ok=True)
    prefix = _docker_prefix(workspace, workspace / "canonical", workspace / "store",
                            name=name, run_id=run_id, launch_token=token,
                            capability=lease.dir / "grant.secret",
                            mediator_url=f"http://host.docker.internal:{info['port']}/v1/mediate",
                            mediator_instance=info["instance"])
    command = ["docker", *prefix[:prefix.index(IMAGE) + 1], "sh", "-c", "sleep 180"]
    container = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 env=_agent_environment())
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            owned, _ = inspect_exact(name, run_id, token)
            if owned == "owned":
                ready.write_text(json.dumps({"pid": os.getpid(), "name": name,
                                             "run_id": run_id, "grant_id": lease.grant_id}) + "\n",
                                 encoding="utf-8", newline="\n")
                break
            if container.poll() is not None:
                raise RuntimeError("agent_container_exited_early")
            time.sleep(.1)
        else:
            raise RuntimeError("agent_container_not_ready")
        container.wait(timeout=180)
    finally:
        if container.poll() is not None:
            lease.finish()


def _journal_count(state: Path) -> int:
    return _call_count(state / "mediator" / "provider-attempts.jsonl")


def _scan_agent_exposure(state: Path, provider_token: str,
                         capabilities: tuple[str, ...]) -> dict:
    """Check persisted agent-visible files and live Docker inspection, never log secrets."""
    inspected = 0
    for side in ("a", "b"):
        inspect = subprocess.run(["docker", "inspect", NAMES[side]],
                                 capture_output=True, timeout=20)
        if inspect.returncode:
            raise RuntimeError("agent_inspection_unavailable")
        if provider_token.encode() in inspect.stdout or any(
                capability.encode() in inspect.stdout for capability in capabilities):
            raise RuntimeError("secret_in_agent_inspection")
        inspected += 1
        for path in (state / ("agent-" + side)).rglob("*"):
            if path.is_file():
                content = path.read_bytes()
                if provider_token.encode() in content or any(
                        capability.encode() in content for capability in capabilities):
                    raise RuntimeError("secret_in_agent_mount")
                inspected += 1
    return {"inspected_locations": inspected, "unexpected_exact_hits": 0,
            "designated_capability_mounts": 2}


def _scan_persisted_exposure(state: Path, provider_token: str,
                             capabilities: tuple[str, ...]) -> dict:
    scanned = 0
    for path in state.rglob("*"):
        if not path.is_file():
            continue
        content = path.read_bytes()
        if provider_token.encode() in content:
            raise RuntimeError("provider_token_in_probe_state")
        designated = (path.name == "grant.secret" and
                      path.parent.parent.name == "leases" and
                      path.parent.parent.parent.name == "lease")
        if not designated and any(capability.encode() in content
                                  for capability in capabilities):
            raise RuntimeError("capability_outside_designated_mount")
        scanned += 1
    return {"files_scanned": scanned, "unexpected_exact_hits": 0}


def _reviewed_record(path: Path, code_sha: str) -> str:
    raw = path.read_bytes()
    value = json.loads(raw)
    if (not isinstance(value, dict) or value.get("identity") != IDENTITY or
            value.get("source_sha") != code_sha or
            value.get("verdict") != "approve"):
        raise RuntimeError("pre_run_review_not_approved")
    return sha256(raw).hexdigest()


def run(state: Path, token_file: Path, code_sha: str, approval: str,
        review_record: Path) -> dict:
    if not approval or approval != IDENTITY:
        raise RuntimeError("specific_live_approval_required")
    if os.name != "nt":
        raise RuntimeError("windows_docker_route_required")
    if state.exists() or any((parent / ".git").exists() for parent in
                             (state.parent, *state.parent.parents)):
        raise RuntimeError("fresh_private_state_outside_checkout_required")
    if _git("rev-parse", "HEAD", cwd=Path(__file__).resolve().parents[2]) != code_sha:
        raise RuntimeError("code_sha_mismatch")
    review_hash = _reviewed_record(review_record, code_sha)
    connection = HostTokenConnection(connection_id=CONNECTION_ID,
                                     generation=GENERATION, repository=REPOSITORY,
                                     token_file=token_file, key="GH_LAOMEDO",
                                     forbidden_mount=state)
    provider_token = connection.token(CONNECTION_ID, GENERATION)
    _preflight(provider_token)
    state.mkdir(parents=True)
    checkout = state / "trusted-checkout"
    commits = _prepare_commits(checkout)
    record = {"identity": IDENTITY, "source_sha": code_sha,
              "repository": REPOSITORY, "baseline": BASELINE,
              "review_record_sha256": review_hash, "commits": commits,
              "planned_effect_ids": [IDENTITY + suffix for suffix in (
                  "-setup-push-a", "-setup-push-b", "-pr-create-a",
                  "-pr-update-a-denied", "-pr-create-b")],
              "events": [], "status": "incomplete",
              "model_turns": 0}
    path = state / "observation.json"

    def save() -> None:
        pending = path.with_suffix(".pending")
        pending.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8", newline="\n")
        os.replace(pending, path)

    save()
    service = runner_a = runner_b = None
    try:
        service = _process("-m", "laomedo.host_services", "--state", str(state),
                           "--repository", REPOSITORY, "--checkout", str(checkout),
                           "--baseline", BASELINE, "--agent-mount", str(state / "agent-a"),
                           "--connection-id", CONNECTION_ID,
                           "--connection-generation", str(GENERATION),
                           "--token-file", str(token_file), "--token-key", "GH_LAOMEDO")
        mediator = _wait(state / "mediator" / "mediator.json")
        lease_service = _wait(state / "lease" / "service.json")
        if (mediator.get("pid") != service.pid or lease_service.get("pid") != service.pid or
                not isinstance(mediator.get("instance"), str)):
            raise RuntimeError("host_service_identity_mismatch")
        authority = RunGrantAuthority(state / "authority.sqlite",
                                      connection_authorizer=connection.authorize)
        for side in ("a", "b"):
            setup_run = IDENTITY + "-setup-" + side
            setup_lease = IDENTITY + "-setup-lease-" + side
            ref = authority.approve(invocation_id="invocation-" + setup_run,
                                    repository=REPOSITORY, branch=BRANCHES[side],
                                    operations={"git_push"}, reviewed_by=IDENTITY,
                                    connection_id=CONNECTION_ID,
                                    connection_generation=GENERATION)
            authority.bind_run(ref, setup_run)
            setup = LeaseClient(state / "lease", run_id=setup_run,
                                name="laomedo-" + setup_run, token=setup_lease,
                                cancelled=threading.Event(), mediation_request={
                                    "invocation_id": "invocation-" + setup_run,
                                    "repository": REPOSITORY, "branch": BRANCHES[side]})
            try:
                before = _journal_count(state)
                status, response = _mediate(mediator["port"], mediator["instance"],
                                            setup.grant_secret(), "git_push",
                                            {"branch": BRANCHES[side],
                                             "commit": commits[side]},
                                            IDENTITY + "-setup-push-" + side)
                record["events"].append({"name": "setup_push_" + side,
                                         "http": status, "state": response.get("state"),
                                         "provider_delta": _journal_count(state) - before})
                save()
                _check_effect(status, response, "setup_push_" + side)
                if _journal_count(state) - before != 1:
                    raise RuntimeError("setup_provider_attempt_count_invalid")
                remote = _api(provider_token, "/repos/" + REPOSITORY +
                              "/git/ref/heads/" + BRANCHES[side])
                if remote.get("object", {}).get("sha") != commits[side]:
                    raise RuntimeError("setup_ref_readback_mismatch")
            finally:
                setup.finish()
        for side in ("a", "b"):
            ref = authority.approve(invocation_id="invocation-" + RUNS[side],
                                    repository=REPOSITORY, branch=BRANCHES[side],
                                    operations={"pr_create", "pr_update"},
                                    reviewed_by=IDENTITY, connection_id=CONNECTION_ID,
                                    connection_generation=GENERATION)
            authority.bind_run(ref, RUNS[side],
                               allowed_operations=frozenset({"pr_create", "pr_update",
                                                             "actions_read"}))
        runner_args = (str(Path(__file__).resolve()), "--runner", "--state", str(state))
        launch_options = ({"creationflags": subprocess.CREATE_NO_WINDOW}
                          if os.name == "nt" else {"start_new_session": True})
        runner_a = subprocess.Popen(
            [sys.executable, *runner_args, "--side", "a", "--ready",
             str(state / "runner-a.json")], env=_agent_environment(),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, **launch_options)
        runner_b = subprocess.Popen(
            [sys.executable, *runner_args, "--side", "b", "--ready",
             str(state / "runner-b.json")], env=_agent_environment(),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, **launch_options)
        for side, process in (("a", runner_a), ("b", runner_b)):
            ready = _wait(state / ("runner-" + side + ".json"))
            if ready.get("pid") != process.pid or ready.get("run_id") != RUNS[side]:
                raise RuntimeError("runner_identity_mismatch")
        capabilities = tuple((state / "lease" / "leases" / LEASES[side] /
                              "grant.secret").read_text(encoding="utf-8")
                             for side in ("a", "b"))
        record["exposure_scan"] = _scan_agent_exposure(state, provider_token, capabilities)
        save()
        title_a = "EXP-104 S7 A " + IDENTITY
        payload_a = {"title": title_a, "body": MARKERS["a"],
                     "head": BRANCHES["a"], "base": "main", "marker": MARKERS["a"]}
        before = _journal_count(state)
        status, response = _container_call(NAMES["a"], "pr_create", payload_a,
                                           IDENTITY + "-pr-create-a",
                                           (provider_token, *capabilities))
        result = _check_effect(status, response, "pr_create_a")
        number_a = result.get("number")
        if type(number_a) is not int or number_a < 1:
            raise RuntimeError("pr_create_a_number_unknown")
        record["events"].append({"name": "pr_create_a", "number": number_a,
                                 "provider_delta": _journal_count(state) - before,
                                 "readback": _remote_pr(provider_token, number_a, "a")})
        save()
        if _journal_count(state) - before != 1:
            raise RuntimeError("a_provider_attempt_count_invalid")
        killed = _kill_runner(runner_a)
        runner_a = None
        record["runner_a_loss"] = killed
        save()
        revoked = _wait(state / "lease" / "leases" / LEASES["a"] / "revoked.json", 40)
        revocation_at = revoked.get("revoked_at_monotonic")
        if (revoked.get("reason") != "heartbeat_lost" or
                not isinstance(revocation_at, (int, float)) or
                revocation_at - killed["completed_monotonic"] > 60 or
                revocation_at < killed["completed_monotonic"]):
            raise RuntimeError("runner_a_revocation_gate_failed")
        record["runner_a_revocation"] = revoked
        save()
        before = _journal_count(state)
        capability_a = (state / "lease" / "leases" / LEASES["a"] /
                        "grant.secret").read_text(encoding="utf-8")
        status, denied = _mediate(mediator["port"], mediator["instance"],
                                  capability_a, "pr_update", {
                                      "number": number_a, "head": BRANCHES["a"],
                                      "base": "main", "marker": MARKERS["a"],
                                      "title": title_a + " SHOULD NOT APPEAR",
                                  }, IDENTITY + "-pr-update-a-denied")
        if (status != 403 or _journal_count(state) != before or
                _remote_pr(provider_token, number_a, "a", title=title_a)["number"] != number_a):
            raise RuntimeError("post_loss_denial_gate_failed")
        record["events"].append({"name": "a_denied", "http": status,
                                 "error": denied.get("error"), "provider_delta": 0})
        save()
        title_b = "EXP-104 S7 B " + IDENTITY
        payload_b = {"title": title_b, "body": MARKERS["b"],
                     "head": BRANCHES["b"], "base": "main", "marker": MARKERS["b"]}
        before = _journal_count(state)
        status, response = _container_call(NAMES["b"], "pr_create", payload_b,
                                           IDENTITY + "-pr-create-b",
                                           (provider_token, *capabilities))
        result = _check_effect(status, response, "pr_create_b")
        number_b = result.get("number")
        if type(number_b) is not int or number_b < 1 or number_b == number_a:
            raise RuntimeError("pr_create_b_number_unknown")
        record["events"].append({"name": "pr_create_b", "number": number_b,
                                 "provider_delta": _journal_count(state) - before,
                                 "readback": _remote_pr(provider_token, number_b, "b")})
        save()
        if _journal_count(state) - before != 1:
            raise RuntimeError("b_provider_attempt_count_invalid")
        stop = subprocess.run(["docker", "stop", NAMES["b"]],
                              capture_output=True, timeout=20)
        if stop.returncode:
            raise RuntimeError("runner_b_container_stop_failed")
        runner_b.wait(timeout=20)
        runner_b = None
        b_result = _wait(state / "lease" / "leases" / LEASES["b"] / "result.json", 20)
        if b_result.get("reason") != "done":
            raise RuntimeError("runner_b_normal_revocation_unverified")
        record["runner_b_result"] = b_result
        record["provider_attempts"] = _journal_count(state)
        if record["provider_attempts"] != 4:
            raise RuntimeError("provider_attempt_total_invalid")
        record["persisted_exposure_scan"] = _scan_persisted_exposure(
            state, provider_token, capabilities)
        record["status"] = "passed"
        save()
        return record
    except BaseException as failure:
        record["status"] = "inconclusive_or_failed"
        record["error_class"] = type(failure).__name__
        record["error_code"] = str(failure) if type(failure) is RuntimeError else "probe_error"
        save()
        raise
    finally:
        # Local shutdown only. Never delete remote refs or retry remote writes.
        for side, process in (("a", runner_a), ("b", runner_b)):
            if process is not None and process.poll() is None:
                try:
                    _kill_runner(process)
                except Exception:
                    pass
            if service is not None and (state / "lease" / "leases" /
                                        LEASES[side] / "accepted.json").exists():
                try:
                    _wait(state / "lease" / "leases" / LEASES[side] / "result.json", 40)
                except Exception:
                    # Preserve the original failure and the private state for audit.
                    pass
        _stop(service)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", action="store_true")
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--side", choices=("a", "b"))
    parser.add_argument("--ready", type=Path)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--source-sha")
    parser.add_argument("--approval-id")
    parser.add_argument("--review-record", type=Path)
    args = parser.parse_args()
    if args.runner:
        if args.side is None or args.ready is None:
            parser.error("runner side and ready path required")
        _agent_runner(args.state, args.side, args.ready)
    else:
        if any(value is None for value in (args.token_file, args.source_sha,
                                           args.approval_id, args.review_record)):
            parser.error("token file, source SHA, approval ID and review record required")
        run(args.state, args.token_file, args.source_sha, args.approval_id,
            args.review_record)


if __name__ == "__main__":
    main()
