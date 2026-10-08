"""One-shot EXP-104 GitHub/runner-loss diagnostic.

The selected token is read only by the credential-owning host process and
read-only preflight. A harness pass is not by itself full protocol acceptance.
Run with an unused state directory outside every checkout. Never rerun a
state directory or automatically retry an uncertain remote effect.
"""

from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
from urllib import error, request

from laomedo.container_lease import cleanup_exact, inspect_exact
from laomedo.github_git_transport import (_base_git_environment,
                                          _credential_environment,
                                          _push_failure_category)
from laomedo.github_mediation import MediationError, MediationStore
from laomedo.host_token_connection import HostTokenConnection
from laomedo.lease_service import LeaseClient
from laomedo.mediation_authority import RunGrantAuthority


REPOSITORY = "ga84jog/laomedo-exp104-disposable-20261007"
REPOSITORY_ID = 1408647759
BASELINE = "1f1a505f2fbd31993a7946924a9bec5a27bb15c1"
IMAGE = "sha256:bb8009c87ab69e751a1dd2c6c7f8abaae3d9fce8e072802d4a23c95594d16d84"
CONNECTION_ID = "exp104-d2-selected-gh"
GENERATION = 1
IDENTITY = "exp104-d2-20261007-02"
BRANCH_A = IDENTITY + "-a"
BRANCH_B = IDENTITY + "-b"
BRANCH_C = IDENTITY + "-c"
BRANCH_A_DENIED = IDENTITY + "-a-denied"
RUN_A = IDENTITY + "-run-a"
RUN_B = IDENTITY + "-run-b"
RUN_C = IDENTITY + "-run-c"
LEASE_A = IDENTITY + "-lease-a"
LEASE_B = IDENTITY + "-lease-b"
LEASE_C = IDENTITY + "-lease-c"
CONTAINER_A = "laomedo-" + IDENTITY + "-a"
CONTAINER_B = "laomedo-" + IDENTITY + "-b"
CONTAINER_C = "laomedo-" + IDENTITY + "-c"
CONSUMED_IDENTITIES = frozenset({
    "exp104-d2-20261007-01", "exp104-d2-20261007-02",
    "exp104-s3-20261007-01", "exp104-s4-20261007-01",
    "exp104-s5-20261007-01",
    "exp104-s6-20261007-01",
})


def select_fresh_identity(identity: str, connection_id: str) -> None:
    """Select a frozen, unused experiment identity before starting anything."""
    import re

    if not re.fullmatch(r"exp104-[a-z0-9-]{8,60}", identity) or \
            not re.fullmatch(r"exp104-[a-z0-9-]{8,60}", connection_id):
        raise ValueError("experiment_identity_invalid")
    if identity in CONSUMED_IDENTITIES:
        raise ValueError("experiment_identity_consumed")
    global IDENTITY, CONNECTION_ID, BRANCH_A, BRANCH_B, BRANCH_C, BRANCH_A_DENIED
    global RUN_A, RUN_B, RUN_C, LEASE_A, LEASE_B, LEASE_C
    global CONTAINER_A, CONTAINER_B, CONTAINER_C
    IDENTITY, CONNECTION_ID = identity, connection_id
    BRANCH_A, BRANCH_B, BRANCH_C = (identity + suffix for suffix in ("-a", "-b", "-c"))
    BRANCH_A_DENIED = identity + "-a-denied"
    RUN_A, RUN_B, RUN_C = (identity + suffix for suffix in ("-run-a", "-run-b", "-run-c"))
    LEASE_A, LEASE_B, LEASE_C = (identity + suffix for suffix in
                               ("-lease-a", "-lease-b", "-lease-c"))
    CONTAINER_A, CONTAINER_B, CONTAINER_C = ("laomedo-" + identity + suffix
                                           for suffix in ("-a", "-b", "-c"))


def _git(*args: str, cwd: Path | None = None) -> str:
    command = ["git", *( ["-C", str(cwd)] if cwd else []), *args]
    result = subprocess.run(command, env=_base_git_environment(),
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError("git_preflight_failed")
    return result.stdout.strip()


def _api(token: str, path: str) -> dict:
    call = request.Request("https://api.github.com" + path, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "laomedo-exp104-d2/0.1"})
    with request.urlopen(call, timeout=15) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise RuntimeError("github_read_invalid")
    return value


def _wait(path: Path, timeout: float = 20) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                return value
        failure_path = path.with_suffix(".error.json")
        if failure_path.is_file():
            failure = json.loads(failure_path.read_text(encoding="utf-8"))
            raise RuntimeError("runner_start_failed:" + failure.get("code", "unknown"))
        time.sleep(.05)
    raise RuntimeError("ready_timeout")


def _runner(state: Path, run_id: str, lease_token: str, name: str,
            branch: str, ready: Path) -> None:
    # This process is the only one killed in the runner-loss case. The
    # mediator and lease service are siblings launched by the controller.
    client = LeaseClient(state, run_id=run_id, name=name, token=lease_token,
                         cancelled=threading.Event(), mediation_request={
                             "invocation_id": "invocation-" + run_id,
                             "repository": REPOSITORY, "branch": branch})
    launched = subprocess.run([
        "docker", "run", "-d", "--name", name, "--network", "none",
        "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--memory", "64m", "--pids-limit", "32",
        "--label", "laomedo.run_id=" + run_id,
        "--label", "laomedo.launch_token=" + lease_token,
        IMAGE, "python", "-c", "import time; time.sleep(180)"],
        env=_base_git_environment(), capture_output=True, timeout=30)
    if launched.returncode:
        (ready.parent / (ready.stem + ".docker-stderr.txt")).write_bytes(launched.stderr)
        raise RuntimeError("container_launch_failed:" + str(launched.returncode))
    owned, _ = inspect_exact(name, run_id, lease_token)
    if owned != "owned":
        raise RuntimeError("container_identity_unverified")
    ready.write_text(json.dumps({"run_id": run_id, "pid": os.getpid(),
                                 "container": name, "grant_id": client.grant_id}) + "\n",
                     encoding="utf-8", newline="\n")
    while True:
        time.sleep(1)


def _mediate(port: int, bearer: str, operation: str, payload: dict,
             effect_id: str | None, *, repository: str = REPOSITORY) -> tuple[int, dict]:
    body = json.dumps({"repository": repository, "operation": operation,
                       "payload": payload, "effect_id": effect_id}).encode()
    call = request.Request(f"http://127.0.0.1:{port}/v1/mediate", data=body,
                           method="POST", headers={"Authorization": "Bearer " + bearer,
                                                   "Content-Type": "application/json"})
    try:
        with request.urlopen(call, timeout=35) as response:
            return response.status, json.load(response)
    except error.HTTPError as failure:
        return failure.code, json.load(failure)


def _process(*args: str, cwd: Path | None = None) -> subprocess.Popen:
    environment = _base_git_environment()
    # PYTHONPATH identifies source code, never a host credential.
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    options = ({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else
               {"start_new_session": True})
    return subprocess.Popen([sys.executable, *args], env=environment, cwd=cwd,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, **options)


def _stop(process: subprocess.Popen | None) -> None:
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=8)


def _checkpoint_and_stop_services(checkpoint, lease, mediator) -> None:
    """Attempt both service stops even if recording or the first stop fails."""
    try:
        checkpoint()
    finally:
        try:
            _stop(lease)
        finally:
            _stop(mediator)


def _kill_runner(process: subprocess.Popen) -> dict:
    if process.poll() is not None:
        raise RuntimeError("runner_not_alive")
    started = time.monotonic()
    if os.name == "nt":
        killed = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                capture_output=True, timeout=15)
        if killed.returncode:
            raise RuntimeError("runner_tree_kill_failed")
    else:
        process.kill()
    process.wait(timeout=15)
    return {"pid": process.pid, "started_monotonic": started,
            "completed_monotonic": time.monotonic(), "completed_wall": time.time()}


def _call_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0


def _safe_call_count(path: Path) -> dict:
    try:
        return {"count": _call_count(path), "error": None}
    except (OSError, UnicodeError):
        return {"count": None, "error": "invalid_or_unavailable"}


def _safe_json_object(path: Path) -> dict:
    try:
        if not path.exists():
            return {"value": None, "error": None}
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return {"value": None, "error": "invalid_or_unavailable"}
        return {"value": value, "error": None}
    except (OSError, UnicodeError, ValueError, RecursionError):
        return {"value": None, "error": "invalid_or_unavailable"}


def _secret_canary(state: Path, token: str) -> dict:
    needle = token.encode("utf-8")
    files = 0
    hits = 0
    for path in state.rglob("*"):
        if path.is_file():
            files += 1
            if needle in path.read_bytes():
                hits += 1
    return {"files_scanned": files, "exact_token_hits": hits}


def _dry_run_preflight(token: str, checkout: Path, commit: str,
                       branch: str, *, run=subprocess.run) -> dict:
    """Check the new ref without sending updates or persisting Git output."""
    ref = "refs/heads/" + branch
    environment, helper = _credential_environment(token)
    try:
        result = run(["git", "-C", str(checkout), "-c", "credential.helper=",
                      "-c", "credential.helper=" + helper, "push", "--dry-run",
                      "--porcelain", "--force-with-lease=" + ref + ":",
                      "https://github.com/" + REPOSITORY + ".git",
                      commit + ":" + ref], env=environment, capture_output=True,
                     timeout=30)
    finally:
        environment.pop("LAOMEDO_MEDIATED_GIT_TOKEN", None)
    return {"exit_code": result.returncode,
            "category": _push_failure_category(result.stderr, result.stdout)
            if result.returncode else None}


def _diagnostic_records(state: Path) -> list[dict]:
    """Allowlist private Git diagnostics before putting them in evidence."""
    path = state / "mediator" / "push-diagnostics.jsonl"
    if not path.exists():
        return []
    allowed = {"authentication_or_authorization", "remote_rejected",
               "network_or_transport", "unclassified"}
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if (not isinstance(value, dict) or
                value.get("category") not in allowed or
                type(value.get("exit_code")) is not int):
            raise RuntimeError("push_diagnostic_invalid")
        records.append({"category": value["category"],
                        "exit_code": value["exit_code"]})
    return records


def _safe_diagnostic_records(state: Path) -> dict:
    try:
        return {"records": _diagnostic_records(state), "error": None}
    except (OSError, UnicodeError, ValueError, TypeError, KeyError,
            RuntimeError):
        return {"records": [], "error": "invalid_or_unavailable"}


def _stored_effect_state(state: Path, run_id: str,
                         effect_id: str) -> dict:
    """Read the mediator's durable effect without opening a write connection."""
    path = (state / "mediator" / "mediator.sqlite").resolve()
    if not path.is_file():
        return {"state": None, "error": None}
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True,
                                     timeout=2)) as db:
            row = db.execute(
                "SELECT state FROM effects WHERE run_id=? AND effect_id=?",
                (run_id, effect_id)).fetchone()
        value = row[0] if row else None
        if value not in {None, "unknown", "confirmed", "rejected"}:
            return {"state": None, "error": "invalid_or_unavailable"}
        return {"state": value, "error": None}
    except (OSError, ValueError, sqlite3.Error):
        return {"state": None, "error": "invalid_or_unavailable"}


def run(state: Path, token_file: Path, code_sha: str, token_key: str,
        scope_confirmation: str | None) -> dict:
    if IDENTITY in CONSUMED_IDENTITIES:
        raise RuntimeError("experiment_identity_consumed")
    if IDENTITY.startswith(("exp104-s3-", "exp104-s4-", "exp104-s5-", "exp104-s6-")) and (
            token_key != "GH_LAOMEDO" or
            scope_confirmation != "selected_repository_only"):
        raise RuntimeError("scoped_identity_confirmation_required")
    if state.exists() or any((parent / ".git").exists() for parent in
                             (state.parent, *state.parent.parents)):
        raise RuntimeError("fresh_private_state_outside_checkout_required")
    if _git("rev-parse", "HEAD", cwd=Path(__file__).resolve().parents[2]) != code_sha:
        raise RuntimeError("code_sha_mismatch")
    state.mkdir(parents=True)
    checkout = state / "trusted-checkout"
    connection = HostTokenConnection(
        connection_id=CONNECTION_ID, generation=GENERATION,
        repository=REPOSITORY, token_file=token_file, key=token_key,
        forbidden_mount=checkout)
    token = connection.token(CONNECTION_ID, GENERATION)
    user = _api(token, "/user")
    repo = _api(token, "/repos/" + REPOSITORY)
    main = _api(token, "/repos/" + REPOSITORY + "/git/ref/heads/main")
    actions = _api(token, "/repos/" + REPOSITORY + "/actions/runs")
    if (user.get("login") != "ga84jog" or repo.get("id") != REPOSITORY_ID or
            main.get("object", {}).get("sha") != BASELINE or
            repo.get("permissions", {}).get("push") is not True or
            type(actions.get("total_count")) is not int):
        raise RuntimeError("github_baseline_mismatch")
    for branch in (BRANCH_A, BRANCH_B, BRANCH_C, BRANCH_A_DENIED):
        try:
            _api(token, "/repos/" + REPOSITORY + "/git/ref/heads/" + branch)
        except error.HTTPError as failure:
            if failure.code != 404:
                raise RuntimeError("branch_preflight_uncertain") from None
        else:
            raise RuntimeError("branch_already_exists")
    # The credential is not passed to Git; this public clone is read-only.
    _git("clone", "--quiet", "https://github.com/" + REPOSITORY + ".git",
         str(checkout))
    if _git("rev-parse", "HEAD", cwd=checkout) != BASELINE:
        raise RuntimeError("clone_baseline_mismatch")
    _git("config", "user.name", "Laomedo EXP-104", cwd=checkout)
    _git("config", "user.email", "exp104@example.invalid", cwd=checkout)
    marker = checkout / "exp104-marker.txt"
    marker.write_text(IDENTITY + "\n", encoding="utf-8", newline="\n")
    _git("add", "exp104-marker.txt", cwd=checkout)
    _git("commit", "-qm", "EXP-104-D2 disposable marker", cwd=checkout)
    commit = _git("rev-parse", "HEAD", cwd=checkout)
    workflow_file = checkout / ".github" / "workflows" / "exp104-control.yml"
    workflow_file.parent.mkdir(parents=True)
    workflow_file.write_text("name: EXP-104 negative control\n", encoding="utf-8", newline="\n")
    _git("add", ".github/workflows/exp104-control.yml", cwd=checkout)
    _git("commit", "-qm", "EXP-104-D2 unpushed workflow negative control", cwd=checkout)
    workflow_commit = _git("rev-parse", "HEAD", cwd=checkout)
    plan = {"diagnostic": IDENTITY, "code_sha": code_sha,
            "repository": REPOSITORY, "repository_id": REPOSITORY_ID,
            "baseline": BASELINE, "commit": commit,
            "workflow_control_commit": workflow_commit,
            "branches": [BRANCH_A, BRANCH_B, BRANCH_C, BRANCH_A_DENIED],
            "run_ids": [RUN_A, RUN_B, RUN_C],
            "connection_id": CONNECTION_ID, "generation": GENERATION,
            "token_key": token_key, "scope_confirmation": scope_confirmation,
            "image": IMAGE, "preflight_wall": time.time()}
    (state / "plan.json").write_text(json.dumps(plan, sort_keys=True, indent=2) + "\n",
                                     encoding="utf-8", newline="\n")

    dry_run = _dry_run_preflight(token, checkout, commit, BRANCH_A)
    (state / "dry-run.json").write_text(
        json.dumps(dry_run, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    if dry_run["exit_code"] != 0:
        raise RuntimeError("dry_run_preflight_failed")
    try:
        _api(token, "/repos/" + REPOSITORY + "/git/ref/heads/" + BRANCH_A)
    except error.HTTPError as failure:
        if failure.code != 404:
            raise RuntimeError("dry_run_ref_readback_uncertain") from None
    else:
        raise RuntimeError("dry_run_created_ref")

    mediator_state = state / "mediator"
    lease_state = state / "lease"
    mediator_state.mkdir()
    ledger = mediator_state / "mediator.sqlite"
    approvals = state / "authority.sqlite"
    authority = RunGrantAuthority(approvals, connection_authorizer=connection.authorize)
    mediator = lease = runner_a = runner_b = runner_c = None
    observation = {"plan": plan, "setup": "README initialized before probe",
                   "events": [], "status": "incomplete"}
    progress_path = state / "progress.json"

    def checkpoint() -> None:
        temporary_path = progress_path.with_suffix(".json.tmp")
        temporary_path.write_text(json.dumps(observation, sort_keys=True, indent=2) + "\n",
                                  encoding="utf-8", newline="\n")
        temporary_path.replace(progress_path)

    checkpoint()
    try:
        mediator = _process("-m", "laomedo.mediation_service",
                            "--state", str(mediator_state), "--repository", REPOSITORY,
                            "--checkout", str(checkout), "--baseline", BASELINE,
                            "--agent-mount", str(checkout), "--connection-id", CONNECTION_ID,
                            "--connection-generation", str(GENERATION),
            "--token-file", str(token_file), "--token-key", token_key)
        info = _wait(mediator_state / "mediator.json")
        if info.get("pid") != mediator.pid or info.get("repository") != REPOSITORY:
            raise RuntimeError("mediator_identity_mismatch")
        lease = _process("-m", "laomedo.lease_service", "serve",
                         "--state", str(lease_state), "--mediator-store", str(ledger),
                         "--authority-store", str(approvals), "--repository", REPOSITORY,
                         "--connection-id", CONNECTION_ID,
                         "--connection-generation", str(GENERATION))
        service = _wait(lease_state / "service.json")
        if service.get("pid") != lease.pid or lease.pid == mediator.pid:
            raise RuntimeError("lease_identity_mismatch")
        observation["service"] = {"lease_pid": lease.pid, "mediator_pid": mediator.pid,
                                  "lease_instance": service["instance"]}
        for run_id, branch in ((RUN_A, BRANCH_A), (RUN_B, BRANCH_B)):
            reference = authority.approve(
                invocation_id="invocation-" + run_id, repository=REPOSITORY,
                branch=branch,
                operations={"git_push"} if run_id == RUN_A else {"actions_read"},
                reviewed_by="user-authorized-" + IDENTITY,
                connection_id=CONNECTION_ID, connection_generation=GENERATION)
            authority.bind_run(reference, run_id)
        runner_args = (str(Path(__file__).resolve()), "--runner", "--state", str(lease_state))
        runner_a = _process(*runner_args, "--run-id", RUN_A, "--lease-token", LEASE_A,
                            "--container", CONTAINER_A, "--branch", BRANCH_A,
                            "--ready", str(state / "runner-a.json"))
        runner_b = _process(*runner_args, "--run-id", RUN_B, "--lease-token", LEASE_B,
                            "--container", CONTAINER_B, "--branch", BRANCH_B,
                            "--ready", str(state / "runner-b.json"))
        ready_a = _wait(state / "runner-a.json")
        ready_b = _wait(state / "runner-b.json")
        if ready_a.get("pid") != runner_a.pid or ready_b.get("pid") != runner_b.pid:
            raise RuntimeError("runner_identity_mismatch")
        bearer_a = (lease_state / "leases" / LEASE_A / "grant.secret").read_text()
        bearer_b = (lease_state / "leases" / LEASE_B / "grant.secret").read_text()
        port = info["port"]
        read_payload = {"resource": "runs"}
        before = _call_count(mediator_state / "provider-attempts.jsonl")
        status, wrong_branch = _mediate(port, bearer_a, "git_push",
                                        {"branch": BRANCH_B, "commit": commit},
                                        IDENTITY + "-wrong-branch")
        if (status != 403 or wrong_branch.get("error") != "push_branch_denied" or
                _call_count(mediator_state / "provider-attempts.jsonl") != before):
            raise RuntimeError("wrong_branch_control_failed")
        observation["events"].append({"name": "wrong_branch_control", "http": status,
                                       "error": wrong_branch.get("error")})
        status, pushed = _mediate(port, bearer_a, "git_push",
                                  {"branch": BRANCH_A, "commit": commit}, IDENTITY + "-push-a")
        observation["events"].append({"name": "a_push", "http": status,
                                       "state": pushed.get("state"), "at_monotonic": time.monotonic()})
        checkpoint()
        if status != 200 or pushed.get("state") != "confirmed":
            raise RuntimeError("a_push_not_confirmed_no_retry")
        remote = _api(token, "/repos/" + REPOSITORY + "/git/ref/heads/" + BRANCH_A)
        observation["remote_ref_a_after_push"] = {
            "sha": remote.get("object", {}).get("sha"), "read_at": time.time()}
        checkpoint()
        if remote.get("object", {}).get("sha") != commit:
            raise RuntimeError("a_ref_readback_mismatch")
        status, read_b = _mediate(port, bearer_b, "actions_read", read_payload, None)
        observation["events"].append({"name": "b_read_before", "http": status,
                                       "state": read_b.get("state"), "at_monotonic": time.monotonic()})
        checkpoint()
        if status != 200 or read_b.get("state") != "confirmed":
            raise RuntimeError("b_read_failed")
        killed = _kill_runner(runner_a)
        observation["runner_loss"] = killed
        checkpoint()
        revoked = _wait(lease_state / "leases" / LEASE_A / "revoked.json", timeout=40)
        observation["lease_revocation_a"] = revoked
        observation["container_a_at_denial"] = inspect_exact(
            CONTAINER_A, RUN_A, LEASE_A)[0]
        checkpoint()
        detected_mono = revoked.get("detected_at_monotonic")
        revoked_mono = revoked.get("revoked_at_monotonic")
        if (revoked.get("reason") != "heartbeat_lost" or
                not isinstance(detected_mono, (int, float)) or
                not isinstance(revoked_mono, (int, float)) or
                not killed["completed_monotonic"] <= detected_mono <= revoked_mono or
                revoked_mono - killed["completed_monotonic"] > 60):
            raise RuntimeError("revocation_gate_failed")
        count_before_denial = _call_count(mediator_state / "provider-attempts.jsonl")
        denial_requested_at_monotonic = time.monotonic()
        status, denied = _mediate(port, bearer_a, "git_push",
                                  {"branch": BRANCH_A_DENIED, "commit": commit},
                                  IDENTITY + "-push-a-denied")
        count_after_denial = _call_count(mediator_state / "provider-attempts.jsonl")
        observation["events"].append({"name": "a_denied_after_loss", "http": status,
                                       "error": denied.get("error"),
                                       "requested_at_monotonic": denial_requested_at_monotonic,
                                       "at_monotonic": time.monotonic(),
                                       "provider_calls_before": count_before_denial,
                                       "provider_calls_after": count_after_denial})
        checkpoint()
        denied_ref_requested_at_monotonic = time.monotonic()
        try:
            _api(token, "/repos/" + REPOSITORY + "/git/ref/heads/" + BRANCH_A_DENIED)
        except error.HTTPError as failure:
            denied_ref_status = failure.code
        else:
            denied_ref_status = 200
        observation["remote_ref_a_denied_branch"] = {
            "branch": BRANCH_A_DENIED, "http": denied_ref_status,
            "requested_at_monotonic": denied_ref_requested_at_monotonic,
            "read_at_monotonic": time.monotonic(), "read_at_wall": time.time()}
        checkpoint()
        if (status != 403 or denied.get("error") != "grant_unavailable" or
                count_after_denial != count_before_denial or
                denied_ref_status != 404):
            raise RuntimeError("post_loss_denial_gate_failed")
        result = _wait(lease_state / "leases" / LEASE_A / "result.json", timeout=40)
        observation["lease_result_a"] = result
        checkpoint()
        cleanup_mono = result.get("cleanup_finished_at_monotonic")
        if (result.get("cleanup_verified") is not True or
                not isinstance(cleanup_mono, (int, float)) or
                cleanup_mono < revoked_mono):
            raise RuntimeError("cleanup_gate_failed")
        status, read_b = _mediate(port, bearer_b, "actions_read", read_payload, None)
        observation["events"].append({"name": "b_read_after", "http": status,
                                       "state": read_b.get("state"), "at_monotonic": time.monotonic()})
        checkpoint()
        if status != 200 or read_b.get("state") != "confirmed":
            raise RuntimeError("b_continuity_failed")
        # Restart only the independent lease service. No old grant may be
        # adopted by the new instance, while the mediator stays running.
        _stop(runner_b)
        runner_b = None
        _stop(lease)
        lease = None
        lease = _process("-m", "laomedo.lease_service", "serve",
                         "--state", str(lease_state), "--mediator-store", str(ledger),
                         "--authority-store", str(approvals), "--repository", REPOSITORY,
                         "--connection-id", CONNECTION_ID,
                         "--connection-generation", str(GENERATION))
        deadline = time.monotonic() + 20
        restarted = None
        while time.monotonic() < deadline:
            candidate = json.loads((lease_state / "service.json").read_text(encoding="utf-8"))
            if candidate.get("pid") == lease.pid:
                restarted = candidate
                break
            time.sleep(.05)
        if restarted is None or restarted.get("instance") == service.get("instance"):
            raise RuntimeError("service_restart_unverified")
        # The startup sweep performs exact-container cleanup and may take
        # several seconds. Do not register C until that sweep has finished:
        # otherwise C's first heartbeat can expire while it waits in the
        # service's scan queue, before it can start its heartbeat thread.
        swept_b = _wait(lease_state / "leases" / LEASE_B / "result.json", timeout=30)
        if (swept_b.get("reason") != "service_restart" or
                swept_b.get("cleanup_verified") is not True):
            raise RuntimeError("startup_sweep_unverified")
        observation["lease_result_b"] = swept_b
        checkpoint()
        status, old_b = _mediate(port, bearer_b, "api_rest_read", read_payload, None)
        if status != 403 or old_b.get("error") != "grant_unavailable":
            raise RuntimeError("old_grant_adopted")
        observation["events"].append({"name": "service_restart_old_b", "http": status,
                                       "error": old_b.get("error"),
                                       "new_instance": restarted["instance"]})
        checkpoint()
        reference = authority.approve(
            invocation_id="invocation-" + RUN_C, repository=REPOSITORY,
            branch=BRANCH_C, operations={"actions_read", "git_push"},
            reviewed_by="user-authorized-" + IDENTITY,
            connection_id=CONNECTION_ID, connection_generation=GENERATION)
        authority.bind_run(reference, RUN_C)
        runner_c = _process(*runner_args, "--run-id", RUN_C, "--lease-token", LEASE_C,
                            "--container", CONTAINER_C, "--branch", BRANCH_C,
                            "--ready", str(state / "runner-c.json"))
        ready_c = _wait(state / "runner-c.json")
        if ready_c.get("pid") != runner_c.pid:
            raise RuntimeError("new_run_identity_mismatch")
        bearer_c = (lease_state / "leases" / LEASE_C / "grant.secret").read_text()
        status, new_c = _mediate(port, bearer_c, "actions_read", read_payload, None)
        if status != 200 or new_c.get("state") != "confirmed":
            raise RuntimeError("new_run_after_restart_failed")
        observation["events"].append({"name": "new_c_read", "http": status,
                                       "state": new_c.get("state")})
        checkpoint()
        before_controls = _call_count(mediator_state / "provider-attempts.jsonl")
        status, workflow = _mediate(port, bearer_c, "git_push",
                                    {"branch": BRANCH_C, "commit": workflow_commit},
                                    IDENTITY + "-workflow-denied")
        status_repo, wrong_repo = _mediate(port, bearer_c, "actions_read",
                                            read_payload, None,
                                            repository="ga84jog/other-disposable")
        missing = authority.authorize_lease(
            {"run_id": "unrecorded-run", "token": "unrecorded-lease"},
            {"invocation_id": "unrecorded-invocation", "repository": REPOSITORY,
             "branch": BRANCH_C})
        after_controls = _call_count(mediator_state / "provider-attempts.jsonl")
        if (status != 403 or workflow.get("error") != "workflow_approval_required" or
                status_repo != 403 or wrong_repo.get("error") != "connection_unavailable" or
                missing is not None or after_controls != before_controls):
            raise RuntimeError("negative_control_failed")
        observation["events"].append({"name": "negative_controls", "workflow_http": status,
                                       "workflow_error": workflow.get("error"),
                                       "missing_run_refused": missing is None,
                                       "provider_delta": after_controls - before_controls})
        # Expiry and lost-response controls use an isolated synthetic store;
        # they must never contact GitHub or consume another live effect.
        synthetic_now = [time.time()]
        synthetic = MediationStore(state / "synthetic-negative.sqlite",
                                   now=lambda: synthetic_now[0])
        _, expired = synthetic.issue(run_id="synthetic-expired", invocation_id="synthetic",
                                     repository=REPOSITORY, operations={"api_rest_read"},
                                     ttl_seconds=1)
        synthetic_now[0] += 2
        synthetic_calls = []
        try:
            synthetic.invoke(token=expired, repository=REPOSITORY,
                             operation="api_rest_read", payload=read_payload,
                             effect_id=None,
                             transport=lambda *args: synthetic_calls.append(args) or {})
        except MediationError as failure:
            if failure.code != "grant_unavailable":
                raise
        else:
            raise RuntimeError("expired_grant_accepted")
        if synthetic_calls:
            raise RuntimeError("expired_grant_reached_provider")
        observation["events"].append({"name": "synthetic_expiry_control",
                                       "provider_calls": len(synthetic_calls)})
        _, uncertain = synthetic.issue(
            run_id="synthetic-unknown", invocation_id="synthetic",
            repository=REPOSITORY, branch=BRANCH_C, operations={"pr_create"},
            ttl_seconds=60)
        ambiguous_calls = []

        def ambiguous_transport(*args):
            ambiguous_calls.append(args)
            raise TimeoutError("synthetic_lost_response")

        unknown_payload = {"head": BRANCH_C, "base": "main", "marker": "synthetic-marker"}
        first_unknown = synthetic.invoke(
            token=uncertain, repository=REPOSITORY, operation="pr_create",
            payload=unknown_payload, effect_id="one-ambiguous-write",
            transport=ambiguous_transport)
        second_unknown = synthetic.invoke(
            token=uncertain, repository=REPOSITORY, operation="pr_create",
            payload=unknown_payload, effect_id="one-ambiguous-write",
            transport=ambiguous_transport)
        if (first_unknown.get("state") != "unknown" or
                second_unknown != {"state": "unknown", "resent": False} or
                len(ambiguous_calls) != 1):
            raise RuntimeError("unknown_effect_was_retried")
        observation["events"].append({"name": "synthetic_lost_response_control",
                                       "transport_calls": len(ambiguous_calls),
                                       "state": second_unknown["state"]})
        observation["provider_attempts"] = _call_count(mediator_state / "provider-attempts.jsonl")
        observation["container_a_after"] = inspect_exact(CONTAINER_A, RUN_A, LEASE_A)[0]
        observation["container_b_after"] = inspect_exact(CONTAINER_B, RUN_B, LEASE_B)[0]
        observation["secret_canary"] = _secret_canary(state, token)
        if observation["secret_canary"]["exact_token_hits"]:
            raise RuntimeError("secret_canary_failed")
        observation["status"] = "scoped_candidate_pending_cleanup" if \
            IDENTITY.startswith(("exp104-s3-", "exp104-s4-", "exp104-s5-", "exp104-s6-")) else \
            "bounded_diagnostic_pending_cleanup"
        checkpoint()
        return observation
    finally:
        try:
            runner_stop_failures = 0
            for process in (runner_a, runner_b, runner_c):
                try:
                    _stop(process)
                except Exception:
                    runner_stop_failures += 1
            observation["runner_stop_failures"] = runner_stop_failures
            cleanup = {}
            for name, run_id, lease_token in ((CONTAINER_A, RUN_A, LEASE_A),
                                              (CONTAINER_B, RUN_B, LEASE_B),
                                              (CONTAINER_C, RUN_C, LEASE_C)):
                try:
                    verified, detail = cleanup_exact(name, run_id, lease_token)
                    state_after, _ = inspect_exact(name, run_id, lease_token)
                    cleanup[name] = {"verified": verified, "detail": detail,
                                     "state_after": state_after}
                except Exception:
                    cleanup[name] = {"verified": False, "detail": "cleanup_error",
                                     "state_after": "unknown"}
            observation["final_container_cleanup"] = cleanup
            if runner_stop_failures:
                observation["status"] = "incomplete"
            elif observation["status"].endswith("pending_cleanup"):
                if all(item["verified"] and item["state_after"] == "absent"
                       for item in cleanup.values()):
                    observation["status"] = ("scoped_candidate_pass" if
                                             IDENTITY.startswith(("exp104-s3-", "exp104-s4-", "exp104-s5-", "exp104-s6-")) else
                                             "bounded_diagnostic_pass")
                else:
                    observation["status"] = "incomplete"
        finally:
            _checkpoint_and_stop_services(checkpoint, lease, mediator)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", action="store_true")
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--token-key", default="GH")
    parser.add_argument("--identity", default=IDENTITY)
    parser.add_argument("--connection-id", default=CONNECTION_ID)
    parser.add_argument("--scope-confirmation",
                        choices=["selected_repository_only"])
    parser.add_argument("--code-sha")
    parser.add_argument("--record", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--lease-token")
    parser.add_argument("--container")
    parser.add_argument("--branch")
    parser.add_argument("--ready", type=Path)
    args = parser.parse_args()
    if args.runner:
        try:
            _runner(args.state, args.run_id, args.lease_token, args.container,
                    args.branch, args.ready)
        except Exception as failure:
            args.ready.with_suffix(".error.json").write_text(
                json.dumps({"code": str(failure) if type(failure) is RuntimeError else
                            type(failure).__name__}) + "\n", encoding="utf-8", newline="\n")
            raise
        return
    if (args.token_file is None or args.code_sha is None or args.record is None or
            args.record.exists() or not args.record.parent.is_dir()):
        parser.error("fresh_record_token_file_and_code_sha_required")
    select_fresh_identity(args.identity, args.connection_id)
    try:
        result = run(args.state.resolve(), args.token_file.resolve(), args.code_sha,
                     args.token_key, args.scope_confirmation)
    except Exception as failure:
        progress = _safe_json_object(args.state / "progress.json")
        plan = _safe_json_object(args.state / "plan.json")
        dry_run = _safe_json_object(args.state / "dry-run.json")
        attempts = _safe_call_count(args.state / "mediator" /
                                    "provider-attempts.jsonl")
        result = {"status": "incomplete", "failure_type": type(failure).__name__,
                  "failure_code": str(failure) if type(failure) is RuntimeError else
                  "external_or_unexpected_error",
                  "progress": progress["value"], "plan": plan["value"],
                  "provider_attempts": attempts["count"],
                  "record_input_errors": [name for name, item in (
                      ("progress", progress), ("plan", plan),
                      ("dry_run", dry_run), ("provider_attempts", attempts))
                      if item["error"]],
                  "push_diagnostics": _safe_diagnostic_records(args.state),
                  "stored_a_push_effect": _stored_effect_state(
                      args.state, RUN_A, IDENTITY + "-push-a"),
                  "dry_run": dry_run["value"]}
        with args.record.open("x", encoding="utf-8", newline="\n") as output:
            output.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
        raise
    with args.record.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "record": str(args.record)}))


if __name__ == "__main__":
    main()
