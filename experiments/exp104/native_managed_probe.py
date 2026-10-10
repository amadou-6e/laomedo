"""Unexecuted S12 controller. Exact-source independent review gates live use."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib import error, request

from experiments.exp104.native_managed_checks import BASELINE, IDENTITY, REPOSITORY, validate
from experiments.exp104 import native_managed_tasks as tasks
from experiments.exp104.native_managed_worker import identities
from laomedo.agent_cli import configure_remote
from laomedo.container_lease import cleanup_exact, inspect_exact
from laomedo.github_git_transport import _base_git_environment
from laomedo.host_token_connection import HostTokenConnection
from laomedo.local_runner import GIT_IMAGE_ID
from laomedo.mediation_authority import RunGrantAuthority

CHECKOUT = Path(__file__).resolve().parents[2]
SPEC_SHA = "ea2558e910d640b802b7b197d2a90b8d14e3249c"


def git(*args, cwd=CHECKOUT):
    result = subprocess.run(["git", *map(str, args)], cwd=cwd,
        env=_base_git_environment(), capture_output=True, timeout=40)
    if result.returncode:
        raise RuntimeError("git_preflight_failed")
    return result.stdout.decode().strip()


def save(path, value):
    pending = path.with_name(path.name + ".pending")
    with pending.open("w", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(value, sort_keys=True, indent=2) + "\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(pending, path)


def api(token, path):
    # Read-only, no caller URL or redirect fallback; credentials stay host-side.
    from laomedo.github_rest_transport import _NoRedirect
    prefix = "/repos/" + REPOSITORY
    if not (path == "/user" or path == prefix or path.startswith(prefix + "/")):
        raise ValueError("preflight_repository_mismatch")
    call = request.Request("https://api.github.com" + path, headers={
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "laomedo-S12"})
    with request.build_opener(_NoRedirect).open(call, timeout=15) as response:
        content = response.read(1024 * 1024 + 1)
        if len(content) > 1024 * 1024:
            raise ValueError("preflight_response_too_large")
        return json.loads(content)


def preflight(token):
    repository = api(token, "/repos/" + REPOSITORY)
    baseline = api(token, "/repos/" + REPOSITORY + "/git/ref/heads/main")
    user = api(token, "/user")
    if (repository.get("id") != 1408647759 or repository.get("default_branch") != "main" or
            repository.get("permissions", {}).get("push") is not True or
            baseline.get("object", {}).get("sha") != BASELINE or user.get("login") != "ga84jog"):
        raise ValueError("preflight_target_mismatch")
    for side in ("a", "b"):
        try:
            api(token, "/repos/" + REPOSITORY + "/git/ref/heads/" + identities(side)["branch"])
        except error.HTTPError as failure:
            if failure.code == 404:
                continue
            raise ValueError("preflight_branch_unknown") from None
        raise ValueError("preflight_branch_exists")
    pulls = api(token, "/repos/" + REPOSITORY + "/pulls?state=all&per_page=100")
    if (not isinstance(pulls, list) or len(pulls) >= 100 or
            any(IDENTITY in str(item.get(field, "")) for item in pulls for field in ("title", "body"))):
        raise ValueError("preflight_marker_unknown")


def require_review(path, source):
    raw = path.read_bytes()
    value = json.loads(raw)
    if (value.get("identity") != IDENTITY or value.get("source_sha") != source or
            value.get("verdict") != "approve"):
        raise ValueError("pre_run_review_required")
    return sha256(raw).hexdigest()


def wait_json(path, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            value = json.loads(path.read_bytes())
            if isinstance(value, dict):
                return value
            raise ValueError("private_state_invalid")
        time.sleep(.1)
    raise TimeoutError("state_deadline")


def journal(root):
    path = root / "host/mediator/provider-attempts.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.is_file() else []


def agent_command(root, side, args, token, capability, *, effect=None, marker=None):
    if time.monotonic() >= float((root / "deadline").read_text()):
        raise TimeoutError("procedure_deadline_no_retry")
    selected = identities(side)
    state, container_id = inspect_exact(selected["name"], selected["run_id"], selected["token"])
    ready = json.loads((root / (side + "-ready.json")).read_bytes())
    if state != "owned" or container_id != ready["container_id"]:
        raise ValueError("container_ownership_changed")
    command = ["docker", "exec", "-i", "--workdir=/draft"]
    if effect is not None:
        command.extend(["--env=LAOMEDO_EFFECT_ID=" + effect,
                        "--env=LAOMEDO_RECONCILIATION_MARKER=" + marker])
    command.extend([selected["name"], *args])
    result = subprocess.run(command, capture_output=True, timeout=120, env=_base_git_environment())
    for secret in (token, capability):
        if secret.encode() in result.stdout + result.stderr:
            raise ValueError("secret_in_agent_command")
    if result.returncode:
        raise RuntimeError("command_unconfirmed_no_retry")
    return result.stdout.decode().strip()


def readiness(root, owned):
    """Both exact task PID sets plus current, same-boot diagnostic origins."""
    expected = os.path.normcase(str(CHECKOUT / "laomedo"))
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        try:
            mediator = json.loads((root / "host/mediator/mediator.json").read_bytes())
            lease = json.loads((root / "host/lease/service.json").read_bytes())
            verifier = json.loads((root / "stages/service-status.json").read_bytes())
            heartbeat = float((root / "host/lease/service.alive.monotonic").read_text())
            pids = {name: tasks.processes(item["configuration"]) for name, item in owned.items()}
            now = time.monotonic()
            if (set(pids) == set(tasks.SERVICES) and all(pids.values()) and
                    mediator["pid"] in pids["host-services"] and lease["pid"] == mediator["pid"] and
                    verifier["pid"] in pids["bundle-verifier"] and
                    os.path.normcase(mediator["module_root"]) == expected and
                    os.path.normcase(verifier["module_root"]) == expected and
                    verifier["phase"] == "idle" and
                    0 <= now - heartbeat < 3 and
                    0 <= now - verifier["scan_completed_monotonic"] < 3):
                return mediator, verifier, pids, heartbeat
        except (OSError, ValueError, KeyError, TypeError):
            pass
        time.sleep(.1)
    raise TimeoutError("managed_services_not_ready")


def kill_worker(process, ready, root, side):
    # Interpreter wrappers can have a child native Python process. Verify
    # the exact ready PID and its parent before killing only the wrapper tree.
    if process.poll() is not None or process.pid == os.getpid():
        raise ValueError("runner_not_alive")
    expected = str(root)
    script = ("$p = Get-CimInstance Win32_Process -Filter " + tasks.quote("ProcessId=" + str(ready["pid"])) +
        "; if (-not $p -or -not $p.CommandLine.Contains('native_managed_worker') "
        "-or -not $p.CommandLine.Contains(" + tasks.quote(expected) + ") "
        "-or -not $p.CommandLine.Contains('--side " + side + "') "
        "-or ($p.ProcessId -ne " + str(process.pid) + " -and $p.ParentProcessId -ne " + str(process.pid) +
        ")) { throw 'runner_identity_changed' }")
    tasks.powershell(script)
    result = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            capture_output=True, timeout=10)
    if result.returncode:
        raise RuntimeError("runner_kill_unknown")
    process.wait(timeout=10)
    return time.monotonic()


def scan_owned(root, token, capabilities):
    hits, files = 0, 0
    needles = [secret.encode() for secret in (token, *capabilities)]
    for base in (root / "runner", root / "stages"):
        for path in base.rglob("*"):
            if path.is_symlink():
                raise ValueError("scan_redirected")
            if path.is_file():
                if path.stat().st_size > 64 * 1024 * 1024:
                    raise ValueError("scan_file_limit")
                content = path.read_bytes()
                files += 1
                hits += sum(bool(needle) and needle in content for needle in needles)
    return files, hits


def run(root, token_file, source, review_record, approval):
    if os.name != "nt" or approval != IDENTITY:
        raise ValueError("approved_windows_capture_required")
    root = root.resolve()
    if (root.exists() or root.name != IDENTITY or
            any((parent / ".git").exists() for parent in root.parents)):
        raise ValueError("fresh_private_root_required")
    if git("rev-parse", "HEAD") != source or git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("clean_reviewed_source_required")
    review_hash = require_review(review_record, source)
    root.mkdir(parents=True)
    with (root / "single-use.claim").open("x") as output:
        output.write(IDENTITY)
    observation = {"identity": IDENTITY, "source_sha": source, "spec_sha": SPEC_SHA,
        "review_record_sha256": review_hash, "repository": REPOSITORY, "baseline": BASELINE,
        "model_turns": 0, "result": "incomplete", "delivery": {}, "cleanup": {}}
    owned, workers, capabilities = {}, {}, {}
    token, authority = None, None
    save(root / "observation.json", observation)
    (root / "deadline").write_text(str(time.monotonic() + 540), encoding="ascii")
    try:
        # The verifier rejects these names. Inspect names, not values, in both
        # logon environments as well as this process before registering tasks.
        denied = ("GH", "GH_TOKEN", "GITHUB_TOKEN", "GH_LAOMEDO", "GIT_ASKPASS")
        if any(key in os.environ for key in denied):
            raise ValueError("credential_environment_present")
        names = ",".join(tasks.quote(key) for key in denied)
        tasks.powershell("foreach ($scope in @('User','Machine')) { foreach ($key in @(" + names +
            ")) { if ([Environment]::GetEnvironmentVariables($scope).Contains($key)) "
            "{ throw 'credential_logon_environment_present' } } }")
        connection = HostTokenConnection(connection_id=IDENTITY + "-connection", generation=1,
            repository=REPOSITORY, token_file=token_file, key="GH_LAOMEDO", forbidden_mount=root)
        token = connection.token(IDENTITY + "-connection", 1)
        preflight(token)
        trusted = root / "trusted"
        git("clone", "--quiet", "https://github.com/" + REPOSITORY + ".git", trusted)
        if git("rev-parse", "HEAD", cwd=trusted) != BASELINE:
            raise ValueError("clone_baseline_changed")
        # Do not trigger an existing workflow as part of this fixture. This
        # is not an attestation about repository secrets or external hooks.
        if (trusted / ".github/workflows").exists():
            raise ValueError("disposable_workflow_exposure_unresolved")
        bundle = root / "baseline.bundle"
        git("bundle", "create", bundle, "refs/heads/main", cwd=trusted)
        if bundle.stat().st_size > 256 * 1024:
            raise ValueError("native_fetch_base_bundle_limit")
        from laomedo.bundle_stage import PINNED_IMAGE_ID
        for image in (GIT_IMAGE_ID, PINNED_IMAGE_ID):
            inspected = subprocess.run(["docker", "image", "inspect", image, "--format", "{{.Id}}"],
                                       capture_output=True, timeout=15)
            if inspected.returncode or inspected.stdout.decode().strip() != image:
                raise ValueError("pinned_image_unavailable")
        for directory in (root / "host", root / "runner", root / "stages"):
            directory.mkdir()
        configs = {
            "host-services": {"state": str(root / "host"), "repository": REPOSITORY,
                "checkout": str(trusted), "baseline": BASELINE, "agent_mount": str(root / "runner"),
                "runner_state": str(root / "runner"), "private_stage": str(root / "stages"),
                "connection_id": IDENTITY + "-connection", "connection_generation": 1,
                "token_file": str(token_file.resolve()), "token_key": "GH_LAOMEDO"},
            "bundle-verifier": {"runner_state": str(root / "runner"), "private_root": str(root / "stages"),
                "agent_mount": str(root / "runner"), "baseline_bundle": str(bundle),
                "baseline_sha256": sha256(bundle.read_bytes()).hexdigest()}}
        for service, configuration in configs.items():
            save(root / (service + ".json"), configuration)
        # Fail before task registration if the task interpreter cannot import
        # this source/dependencies; no package installation or login fallback.
        checked = subprocess.run([sys.executable, "-c", "import laomedo.managed_service; import laomedo.local_runner"],
            cwd=CHECKOUT, env=_base_git_environment(), capture_output=True, timeout=15)
        if checked.returncode:
            raise ValueError("task_interpreter_dependencies_missing")
        tasks.register(root, sys.executable, owned)
        mediator, verifier, before, initial_heartbeat = readiness(root, owned)
        authority = RunGrantAuthority(root / "host/authority.sqlite", connection_authorizer=connection.authorize)
        for side in ("a", "b"):
            selected = identities(side)
            workspace = root / "runner/runs" / selected["run_id"] / "workspace"
            workspace.parent.mkdir(parents=True)
            git("clone", "--quiet", "--no-local", trusted, workspace)
            git("checkout", "--quiet", "-b", selected["branch"], BASELINE, cwd=workspace)
            configure_remote(workspace, REPOSITORY)
            reference = authority.approve(invocation_id=selected["invocation_id"], repository=REPOSITORY,
                branch=selected["branch"], base_branch="main", reviewed_by="operator-approved-S12",
                operations={"git_push", "git_fetch", "pr_create", "pr_update", "pr_read"},
                connection_id=IDENTITY + "-connection", connection_generation=1)
            authority.bind_run(reference, selected["run_id"])
            workers[side] = subprocess.Popen([sys.executable, "-m", "experiments.exp104.native_managed_worker",
                "--root", str(root), "--side", side], cwd=CHECKOUT, env=_base_git_environment(),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            ready = wait_json(root / (side + "-ready.json"))
            capabilities[side] = (root / "host/lease/leases" / selected["token"] / "grant.secret").read_text()
            marker = "laomedo:" + IDENTITY + ":pr:" + side
            command = lambda args, **kw: agent_command(root, side, args, token, capabilities[side], **kw)
            command(["git", "fetch", "origin"])
            file = workspace / ("exp104-native-managed-" + side + ".txt")
            file.write_text(marker + "\n", encoding="utf-8", newline="\n")
            command(["git", "add", file.name])
            command(["git", "-c", "user.name=Laomedo fixture", "-c", "user.email=fixture@example.invalid",
                     "commit", "--quiet", "-m", "S12 disposable fixture"])
            commit = command(["git", "rev-parse", "HEAD"])
            observation["delivery"][side] = {"commit": commit, "branch": selected["branch"], "base": "main",
                "marker": marker, "grant_id": ready["grant_id"], "runner_pid": ready["pid"]}
            save(root / "observation.json", observation)
            command(["git", "push", "origin", "HEAD:refs/heads/" + selected["branch"]])
            if side == "a":
                deliver_pr(root, side, command, observation)
        # B push is confirmed, B PR creation deliberately waits until A denial.
        ready_a = json.loads((root / "a-ready.json").read_bytes())
        killed = kill_worker(workers["a"], ready_a, root, "a")
        revoked = wait_json(root / "host/lease/leases" / identities("a")["token"] / "revoked.json", timeout=60)
        if ready_a["grant_id"] not in revoked["revoked_grants"]:
            raise ValueError("wrong_grant_revoked")
        if not 0 <= revoked["revoked_at_monotonic"] - killed <= 60:
            raise ValueError("revocation_deadline_failed")
        prior = journal(root)
        current_a = api(token, "/repos/" + REPOSITORY + "/pulls/" + str(observation["delivery"]["a"]["pr_number"]))
        payload = {"number": current_a["number"], "head": identities("a")["branch"], "base": "main",
            "title": "S12 denied correction", "body": observation["delivery"]["a"]["marker"],
            "marker": observation["delivery"]["a"]["marker"], "expected": {"title": current_a["title"],
                "body": current_a["body"], "head_sha": current_a["head"]["sha"]}}
        status, denied = refuse_update(mediator, capabilities["a"], payload)
        denied_at = time.monotonic()
        after = journal(root)
        unchanged = api(token, "/repos/" + REPOSITORY + "/pulls/" + str(current_a["number"]))
        from contextlib import closing
        from laomedo.github_mediation import MediationStore
        store = MediationStore(root / "host/mediator/mediator.sqlite", connection_is_current=connection.current)
        with closing(store._connect()) as db:
            b_grant = store._grant(db, capabilities["b"], REPOSITORY, "pr_create")
            b_active = b_grant["run_id"] == identities("b")["run_id"]
        observation["loss"] = {"kill_completed": killed, "revoked": revoked["revoked_at_monotonic"],
            "denied": denied_at, "denial_status": status, "denial_error": denied.get("error"),
            "attempts_before_denial": len(prior), "attempts_after_denial": len(after),
            "pr_unchanged": all(current_a[key] == unchanged[key] for key in ("title", "body")),
            "b_grant_active": b_active, "b_create_after_denial": False}
        if status != 403 or denied.get("error") != "grant_unavailable" or prior != after or not b_active:
            raise ValueError("denial_control_failed_no_retry")
        command_b = lambda args, **kw: agent_command(root, "b", args, token, capabilities["b"], **kw)
        deliver_pr(root, "b", command_b, observation)
        b_creation = [entry for entry in journal(root) if entry["operation"] == "pr_create"][-1]
        observation["loss"]["b_create_after_denial"] = b_creation["at_monotonic"] > denied_at
        observation["loss"]["b_create_intent_monotonic"] = b_creation["at_monotonic"]
        _, _, after_pids, heartbeat = readiness(root, owned)
        observation["tasks"] = {name: {"before": before[name], "after": after_pids[name],
            **tasks.evidence(name, owned[name])} for name in tasks.SERVICES}
        observation["heartbeat_advanced"] = heartbeat > initial_heartbeat
        observation["scanned_files"], observation["unexpected_secret_hits"] = scan_owned(root, token, capabilities.values())
        observation["result"] = "pending_cleanup"
    except Exception as failure:
        observation.update(result="incomplete", failure_class=type(failure).__name__)
    finally:
        cleanup_capture(root, owned, workers, observation)
        observation["provider_mutations"] = [entry for entry in journal(root)
            if entry["operation"] in {"git_push", "pr_create", "pr_update", "issue_create"}]
        if observation["result"] == "pending_cleanup":
            try:
                validate(observation)
                observation["result"] = "passed"
            except Exception as failure:
                observation.update(result="incomplete", failure_class=type(failure).__name__)
        save(root / "observation.json", observation)
    return observation


def deliver_pr(root, side, command, observation):
    item = observation["delivery"][side]
    marker = item["marker"]
    title, body = "S12 disposable " + side, marker + "\nManaged native fixture, no model."
    # Persist planned identity before the command; the broker persists the
    # exact request intent before transport. Never invent a replacement ID.
    item["create_effect_id"] = IDENTITY + "-pr-create-" + side
    save(root / "observation.json", observation)
    created = json.loads(command(["gh", "pr", "create", "--title", title, "--body", body,
        "--head", item["branch"], "--base", "main"], effect=item["create_effect_id"], marker=marker))
    number = created.get("number")
    if type(number) is not int or number < 1:
        raise ValueError("created_pr_unknown_no_retry")
    readback = json.loads(command(["gh", "pr", "view", str(number)]))
    if (readback.get("number") != number or readback.get("title") != title or
            readback.get("body") != body or readback.get("base") != "main" or
            readback.get("head") != {"repository": REPOSITORY, "branch": item["branch"], "sha": item["commit"]}):
        raise ValueError("pr_readback_mismatch_no_retry")
    item.update(pr_number=number, readback_commit=readback["head"]["sha"],
                readback_matches=True, commands_confirmed=True, container_owned_alive=True)
    save(root / "observation.json", observation)


def refuse_update(mediator, capability, payload):
    from laomedo.github_rest_transport import _NoRedirect
    call = request.Request(f"http://127.0.0.1:{mediator['port']}/v1/mediate",
        data=json.dumps({"repository": REPOSITORY, "operation": "pr_update", "payload": payload,
                         "effect_id": IDENTITY + "-denied-update-a"}).encode(), method="POST",
        headers={"Authorization": "Bearer " + capability, "Content-Type": "application/json",
                 "X-Laomedo-Mediator-Instance": mediator["instance"]})
    try:
        with request.build_opener(_NoRedirect).open(call, timeout=20) as response:
            return response.status, json.load(response)
    except error.HTTPError as failure:
        return failure.code, json.load(failure)


def cleanup_capture(root, owned, workers, observation):
    from contextlib import closing
    from laomedo.github_mediation import MediationStore
    from experiments.exp104.probe_active_delivery import stage_cleanup
    cleanup = observation["cleanup"]
    cleanup["grants"] = False
    path = root / "host/mediator/mediator.sqlite"
    try:
        if path.exists():
            store = MediationStore(path)
            for side in ("a", "b"):
                store.revoke_run(identities(side)["run_id"])
            with closing(store._connect()) as db:
                cleanup["grants"] = not db.execute(
                    "SELECT 1 FROM grants WHERE run_id IN (?,?) AND revoked_at IS NULL",
                    (identities("a")["run_id"], identities("b")["run_id"])).fetchone()
        else:
            cleanup["grants"] = True  # No broker initialized, no grant issued.
    except Exception:
        pass
    for side in ("a", "b"):
        selected = identities(side)
        cleanup[side], _ = cleanup_exact(selected["name"], selected["run_id"], selected["token"])
    worker_cleanup = True
    for worker in workers.values():
        try:
            try:
                worker.wait(timeout=20)
            except subprocess.TimeoutExpired:
                # The live Popen handle still identifies the exact fixture we
                # started. Kill its bounded tree, never enumerate unrelated PIDs.
                if worker.poll() is None:
                    result = subprocess.run(["taskkill", "/PID", str(worker.pid), "/T", "/F"],
                                            capture_output=True, timeout=10)
                    worker_cleanup = worker_cleanup and result.returncode == 0
                    worker.wait(timeout=10)
        except Exception:
            worker_cleanup = False
    task_cleanup = tasks.cleanup(owned)
    cleanup["tasks"] = all(task_cleanup.values())
    cleanup["processes"] = worker_cleanup and all(task_cleanup.values())
    if (root / "stages").is_dir():
        cleanup["stages"], observation["stage_cleanup_reports"] = stage_cleanup(root / "stages", None)
    else:
        cleanup["stages"] = True
    if any(value is not True for value in cleanup.values()):
        observation["result"] = "cleanup_unverified"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--source-sha")
    parser.add_argument("--review-record", type=Path)
    parser.add_argument("--approval-id")
    args = parser.parse_args()
    if not args.run or any(item is None for item in (
            args.root, args.token_file, args.source_sha, args.review_record, args.approval_id)):
        parser.error("explicit run, fresh root, token reference, exact source, review and approval required")
    try:
        outcome = run(args.root, args.token_file, args.source_sha, args.review_record, args.approval_id)
        print(json.dumps({"result": outcome["result"], "identity": outcome["identity"]}))
    except Exception as failure:
        # A bookkeeping/cleanup failure may occur after an effect. Never
        # claim definitely undispatched from the outer exception alone.
        print(json.dumps({"result": "unconfirmed", "error_class": type(failure).__name__}))
        raise SystemExit(1)
