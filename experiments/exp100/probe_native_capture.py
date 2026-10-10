"""Single-use S10 local-provider capture; no real token or model turn."""
from hashlib import sha256
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import time

CHECKOUT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CHECKOUT))
from experiments.exp104.probe_active_delivery import FakeGitHub, git, stage_cleanup, refusal_code
from laomedo.agent_cli import configure_remote, prepare_commands
from laomedo.bundle_verifier import BundleVerifier
from laomedo.container_lease import cleanup_exact, inspect_exact, LABEL_RUN, LABEL_TOKEN
from laomedo.github_git_transport import GitHubGitTransport, GitHubMediatedTransport, _base_git_environment
from laomedo.github_rest_transport import GitHubRestTransport
from laomedo.github_mediation import MediationStore
from laomedo.local_runner import GIT_IMAGE_ID
from laomedo.mediation_authority import RunGrantAuthority
from laomedo.mediation_service import MediationHTTPService
from laomedo.verified_git_stage import make_grant_stage_resolver, make_grant_bundle_freezer, classify_verified_workflow

IDENTITY = "exp100-native-s10-20261010-b"
RUN_ID = IDENTITY + "-run"
REPOSITORY = "example/disposable"
SPEC_SHA = "484451161e957f2d7cfafead9a92e27e43493d6e"


def validate_observation(observation):
    """Check captured values, not fixed success labels; also used by controls."""
    pushes = [call for call in observation["git_calls"] if call["command"] == "push"]
    if ([call["target"] for call in pushes] != [commit + ":refs/heads/run-branch"
            for commit in (observation["first"], observation["second"])] or
            sum(call["method"] == "POST" for call in observation["rest_calls"]) != 1 or
            observation["provider_commit"] != observation["second"] or
            observation["provider_body"] != observation["finalBody"] or
            observation["fetchedBase"] != observation["baseline"] or
            observation["agent_owned"] is not True or observation["agent_alive"] is not True or
            observation["checkoutClean"] is not True):
        raise ValueError("positive_capture_mismatch")
    effects = observation["push_effects"]
    if len(effects) != 2 or any(effect["state"] != "confirmed" or
            json.loads(effect["result_json"]).get("commit") != commit
            for effect, commit in zip(effects, (observation["first"], observation["second"]))):
        raise ValueError("push_effect_mismatch")
    commands = observation["outcomes"]
    refusals = [item for item in commands if item["status"] != 0]
    if (len(refusals) != 5 or any(type(item["status"]) is not int or item["status"] == 0
            for item in refusals[:3]) or [item["status"] for item in refusals[3:]] != [2, 3] or
            not all(any(item["command"] == "git" and word in item["args"] for item in refusals)
                    for word in ("--force", "HEAD:refs/heads/other"))):
        raise ValueError("refusal_capture_mismatch")
    if observation["negative_controls"] != {"completed_push": "push_stage_unverified",
            "changed_connection": "connection_unavailable", "revoked_read": "grant_unavailable",
            "completed_freeze_error": "run_grant_mismatch", "completed_freeze_state": "unknown",
            "completed_freeze_created": False, "revoked_update": "grant_unavailable",
            "provider_count_unchanged": True}:
        raise ValueError("negative_capture_mismatch")


def run(private, source_sha):
    if os.name != "nt" or git(CHECKOUT, "rev-parse", "HEAD") != source_sha:
        raise ValueError("source_or_platform_mismatch")
    if subprocess.run(["git", "status", "--porcelain"], cwd=CHECKOUT,
                      capture_output=True, check=True).stdout.strip():
        raise ValueError("source_not_clean")
    private.mkdir(parents=True, exist_ok=True)
    with (private / (IDENTITY + ".claim")).open("x") as output:
        output.write(IDENTITY)
    root = Path(tempfile.mkdtemp(prefix=IDENTITY + "-"))
    observation = {"identity": IDENTITY, "source_sha": source_sha, "spec_sha": SPEC_SHA, "image": GIT_IMAGE_ID,
        "result": "failed", "model_turns": 0, "real_provider_calls": 0}
    server, agent, verifier_thread = None, None, None
    fake, workspace = None, None
    git_calls = []
    stopped = threading.Event()
    stage = root / "private"
    name, launch = "laomedo-codex-" + secrets.token_hex(8), secrets.token_hex(16)
    try:
        trusted, remote, runner = (root / n for n in ("trusted", "remote.git", "runner"))
        trusted.mkdir(); remote.mkdir(); stage.mkdir()
        git(trusted, "init", "--quiet", "-b", "develop")
        (trusted / "base.txt").write_text("baseline\n", encoding="ascii", newline="\n")
        git(trusted, "add", "base.txt")
        git(trusted, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "commit", "--quiet", "-m", "base")
        baseline = git(trusted, "rev-parse", "HEAD")
        bundle = root / "baseline.bundle"
        git(trusted, "bundle", "create", str(bundle), "refs/heads/develop")
        git(remote, "init", "--bare", "--quiet")
        git(trusted, "push", str(remote), "HEAD:refs/heads/develop")
        workspace = runner / "runs" / RUN_ID / "workspace"
        workspace.parent.mkdir(parents=True)
        subprocess.run(["git", "clone", "--quiet", "--no-local", str(trusted), str(workspace)],
                       check=True, capture_output=True, env=_base_git_environment())
        git(workspace, "checkout", "--quiet", "-b", "run-branch")
        git(workspace, "remote", "remove", "origin")
        configure_remote(workspace, REPOSITORY)
        wrappers = prepare_commands(root, REPOSITORY, "run-branch")
        current = {"value": True}
        fake = FakeGitHub(remote)
        def provider(args, **options):
            url = "https://github.com/example/disposable.git"
            revised = [str(remote) if item == url else item for item in args]
            if any(command in args for command in ("push", "fetch", "ls-remote")) and url in args:
                command = next(value for value in ("push", "fetch", "ls-remote") if value in args)
                git_calls.append({"command": command, "target": args[-1]})
            return subprocess.run(revised, **options)
        def credential(cid, generation):
            if (cid, generation) != (IDENTITY, 1) or not current["value"]:
                raise KeyError("connection_invalid")
            return "synthetic-host-only-credential"
        transport = GitHubMediatedTransport(
            GitHubGitTransport(REPOSITORY, trusted, baseline, credential,
                               run=provider, require_verified_stage=True),
            GitHubRestTransport(REPOSITORY, credential, opener=fake))
        store = MediationStore(root / "effects.sqlite",
            verified_stage_resolver=make_grant_stage_resolver(runner, stage, runner),
            stage_freezer=make_grant_bundle_freezer(runner, stage, runner,
                confirmed_stage_authorizer=lambda grant, snapshot: store.confirmed_stage(grant, snapshot)),
            verified_workflow_classifier=classify_verified_workflow,
            connection_is_current=lambda cid, gen, repo: current["value"] and
                (cid, gen, repo) == (IDENTITY, 1, REPOSITORY))
        # Trusted approval is consumed once. Synthetic connection, no account login.
        authority = RunGrantAuthority(root / "authority.sqlite",
            connection_authorizer=lambda *_: True)
        approval = authority.approve(invocation_id=IDENTITY + "-invocation", repository=REPOSITORY,
            branch="run-branch", base_branch="develop", reviewed_by="scripted-controller",
            operations={"git_push", "git_fetch", "pr_create", "pr_update", "pr_read"},
            connection_id=IDENTITY, connection_generation=1)
        scope = authority.bind_run(approval, RUN_ID)
        selected = authority.authorize_lease({"run_id": RUN_ID, "token": IDENTITY + "-lease"}, scope)
        grant, token = store.issue(run_id=RUN_ID, invocation_id=selected["invocation_id"],
            repository=selected["repository"], branch=selected["branch"], base_branch=selected["base_branch"],
            operations=selected["operations"], ttl_seconds=60, connection_id=IDENTITY,
            connection_generation=1)
        record_path = workspace.parent / "record.json"
        record = {"run_id": RUN_ID, "status": "running", "workspace_mode": "git",
            "git_baseline": baseline, "github_scope": scope,
            "container_ownership": {"name": name, "launch_token": launch, "grant_id": grant,
                "supervised": True, "cleanup_verified": False}}
        record_path.write_text(json.dumps(record), encoding="utf-8", newline="\n")
        capability = root / "capability"
        capability.write_text(token, encoding="ascii")
        server = MediationHTTPService(store, transport)
        threading.Thread(target=server.serve, daemon=True).start()
        verifier = BundleVerifier(runner, stage, agent_mount=runner, baseline_bundle=bundle,
                                  baseline_sha256=sha256(bundle.read_bytes()).hexdigest())
        verifier_thread = threading.Thread(target=verifier.serve, args=(stopped,), daemon=True)
        verifier_thread.start()
        command = ["docker", "run", "--name", name, "--pull=never", "--network=bridge",
            "--label", LABEL_RUN + "=" + RUN_ID, "--label", LABEL_TOKEN + "=" + launch,
            "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user=10001:10001",
            "--pids-limit=128", "--memory=1g", "--tmpfs=/tmp:rw,noexec,nosuid,size=64m",
            "--env=GIT_CONFIG_GLOBAL=/dev/null", "--env=GIT_CONFIG_NOSYSTEM=1",
            "--env=PATH=/run/laomedo/bin:/usr/local/bin:/usr/bin:/bin",
            "--env=LAOMEDO_REPOSITORY=" + REPOSITORY, "--env=LAOMEDO_RUN_BRANCH=run-branch",
            "--env=LAOMEDO_BASE_BRANCH=develop",
            "--env=LAOMEDO_MEDIATOR_URL=http://host.docker.internal:" + str(server.port) + "/v1/mediate",
            "--env=LAOMEDO_MEDIATOR_INSTANCE=" + server.instance,
            "--env=LAOMEDO_CAPABILITY_FILE=/run/laomedo/capability", "--workdir=/draft"]
        for source, target, readonly in ((workspace, "/draft", False), (capability, "/run/laomedo/capability", True),
                (wrappers, "/run/laomedo/bin", True),
                (CHECKOUT / "laomedo/agent_mediation_client.mjs", "/run/laomedo/mediate.mjs", True),
                (CHECKOUT / "laomedo/agent_gh_adapter.mjs", "/run/laomedo/gh.mjs", True),
                (CHECKOUT / "laomedo/agent_git_remote.mjs", "/run/laomedo/git-remote.mjs", True),
                (Path(__file__).with_name("native_capture_fixture.mjs"), "/run/laomedo/fixture.mjs", True)):
            command.extend(["--mount", "type=bind,source=" + str(source) + ",target=" + target +
                            (",readonly" if readonly else "")])
        command.extend([GIT_IMAGE_ID, "node", "/run/laomedo/fixture.mjs"])
        agent = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        started = time.monotonic()
        deadline = started + 180
        next_renewal = started + 10
        observation["synthetic_grant_renewals_seconds"] = []
        result_file = workspace / ".git/native-result.json"
        while not result_file.exists() and time.monotonic() < deadline:
            if agent.poll() is not None:
                raise RuntimeError("fixture_exited_no_retry")
            if time.monotonic() >= next_renewal:
                state, _ = inspect_exact(name, RUN_ID, launch)
                if state != "owned" or not store.renew_grant(grant, 60):
                    raise RuntimeError("synthetic_owned_grant_renewal_failed")
                observation["synthetic_grant_renewals_seconds"].append(time.monotonic() - started)
                next_renewal = time.monotonic() + 10
            time.sleep(.1)
        if not result_file.exists():
            raise RuntimeError("capture_pending_no_retry")
        result = json.loads(result_file.read_bytes())
        owned, _ = inspect_exact(name, RUN_ID, launch)
        pushes = [entry for entry in git_calls if entry["command"] == "push"]
        observation.update(result, baseline=baseline, agent_owned=owned == "owned",
            agent_alive=agent.poll() is None, git_calls=git_calls, rest_calls=list(fake.calls),
            provider_commit=git(remote, "rev-parse", "refs/heads/run-branch"),
            provider_body=fake.pr["body"],
            push_effects=[{"effect_id": "native-" + sha256(
                (REPOSITORY + "\nrun-branch\n" + commit).encode()).hexdigest(),
                **store.effect(RUN_ID, "native-" + sha256(
                (REPOSITORY + "\nrun-branch\n" + commit).encode()).hexdigest())}
                for commit in (result["first"], result["second"])])
        if (owned != "owned" or agent.poll() is not None or len(pushes) != 2 or
                result["fetchedBase"] != baseline or git(remote, "rev-parse", "refs/heads/run-branch") != result["second"] or
                fake.pr["body"] != result["finalBody"] or fake.pr["base"]["ref"] != "develop" or
                sum(call["method"] == "POST" for call in fake.calls) != 1):
            raise RuntimeError("positive_control_failed")
        before = len(fake.calls) + len(git_calls)
        record["status"] = "completed"
        record_path.write_text(json.dumps(record), encoding="utf-8", newline="\n")
        def code(op, payload, effect=None):
            return refusal_code(store, token=token, repository=REPOSITORY, operation=op,
                                payload=payload, effect_id=effect, transport=transport)
        try:
            store.stage_freezer({"run_id": RUN_ID, "grant_id": grant,
                "repository": REPOSITORY, "branch": "run-branch"}, {"attempt_id": "completed-freeze"})
            freeze_error = None
        except Exception as failure:
            freeze_error = str(failure)
        freeze_result = store.invoke(token=token, repository=REPOSITORY, operation="bundle_freeze",
            payload={"attempt_id": "completed-freeze"}, effect_id=None, transport=transport)
        push_error = code("git_push", {"branch": "run-branch", "commit": result["second"],
            "stage_attempt_id": observation["push_effects"][1]["effect_id"]}, "completed-push")
        current["value"] = False
        connection_error = code("pr_read", {"number": 7})
        current["value"] = True
        store.revoke_run(RUN_ID)
        revoke_error = code("pr_read", {"number": 7})
        update_error = code("pr_update", {"number": 7, "head": "run-branch", "base": "develop",
            "title": fake.pr["title"], "body": result["finalBody"], "marker": IDENTITY,
            "expected": {"title": fake.pr["title"], "body": result["finalBody"],
                         "head_sha": result["second"]}}, "revoked-update")
        observation["negative_controls"] = {"completed_push": push_error,
            "changed_connection": connection_error, "revoked_read": revoke_error,
            "completed_freeze_error": freeze_error, "completed_freeze_state": freeze_result.get("state"),
            "completed_freeze_created": (stage / RUN_ID / "completed-freeze").exists(),
            "revoked_update": update_error,
            "provider_count_unchanged": before == len(fake.calls) + len(git_calls)}
        if (push_error != "push_stage_unverified" or connection_error != "connection_unavailable" or
                revoke_error != "grant_unavailable" or before != len(fake.calls) + len(git_calls)):
            raise RuntimeError("negative_control_failed")
        validate_observation(observation)
        observation["result"] = "passed"
    except Exception as failure:
        observation["failure_class"] = type(failure).__name__
    finally:
        observation["git_calls"] = list(git_calls)
        observation["rest_calls"] = list(fake.calls) if fake is not None else []
        if workspace is not None and (workspace / ".git/native-progress.json").is_file():
            observation["command_progress"] = json.loads((workspace / ".git/native-progress.json").read_bytes())
        observation["agent_cleanup_verified"], _ = cleanup_exact(name, RUN_ID, launch)
        if agent is not None:
            try:
                agent.wait(timeout=10)
            except subprocess.TimeoutExpired:
                agent.kill(); agent.wait(timeout=5)
            again, _ = cleanup_exact(name, RUN_ID, launch)
            observation["agent_cleanup_verified"] = observation["agent_cleanup_verified"] and again
        stopped.set()
        if verifier_thread:
            verifier_thread.join(timeout=60)
        observation["stage_cleanup_verified"], observation["stage_cleanup_reports"] = stage_cleanup(stage, verifier_thread)
        observation["cleanup_verified"] = observation["agent_cleanup_verified"] and observation["stage_cleanup_verified"]
        if server:
            server.close()
        if not observation["cleanup_verified"]:
            observation["result"] = "cleanup_unverified"
        with (private / (IDENTITY + ".json")).open("x", encoding="utf-8", newline="\n") as output:
            json.dump(observation, output, sort_keys=True, indent=2); output.write("\n")
    return observation


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-state", required=True, type=Path)
    parser.add_argument("--source-sha", required=True)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.private_state, arguments.source_sha), sort_keys=True))
