"""Frozen no-model active-container delivery with explicit fake connectors."""
from hashlib import sha256
import argparse
import io
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
from laomedo.bundle_stage import PINNED_IMAGE_ID
from laomedo.bundle_verifier import BundleVerifier
from laomedo.container_lease import cleanup_exact, inspect_exact, LABEL_RUN, LABEL_TOKEN
from laomedo.github_git_transport import GitHubGitTransport, GitHubMediatedTransport, _base_git_environment
from laomedo.github_rest_transport import GitHubRestTransport
from laomedo.github_mediation import MediationStore, MediationError
from laomedo.mediation_service import MediationHTTPService
from laomedo.verified_git_stage import make_grant_stage_resolver, make_grant_bundle_freezer, classify_verified_workflow

IDENTITY = "exp104-delivery-s1-20261009"
REPOSITORY = "example/disposable"
FIXTURE = Path(__file__).with_name("active_delivery_fixture.mjs")


def git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], check=True,
                          capture_output=True, env=_base_git_environment()).stdout.decode().strip()


class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *_): self.close()


class FakeGitHub:
    def __init__(self, remote):
        self.remote, self.pr = remote, None
        self.calls = []

    def open(self, request, timeout):
        method = request.get_method()
        body = json.loads(request.data) if request.data else None
        self.calls.append({"method": method, "path": request.full_url.removeprefix("https://api.github.com")})
        if request.full_url not in {"https://api.github.com/repos/example/disposable/pulls",
                                    "https://api.github.com/repos/example/disposable/pulls/7"}:
            raise ValueError("fake_target_invalid")
        if method == "POST":
            if self.pr is not None:
                raise ValueError("unexpected_second_create")
            self.pr = {"number": 7, "state": "open", "title": body["title"], "body": body["body"],
                       "base": {"ref": body["base"]},
                       "head": {"repo": {"full_name": REPOSITORY}, "ref": body["head"]}}
        elif method == "PATCH":
            self.pr.update({k: v for k, v in body.items() if k != "base"})
            if "base" in body: self.pr["base"] = {"ref": body["base"]}
        elif method != "GET":
            raise ValueError("fake_method_invalid")
        if self.pr is None: raise ValueError("fake_pr_missing")
        self.pr["head"]["sha"] = git(self.remote, "rev-parse", "refs/heads/" + self.pr["head"]["ref"])
        return Response(json.dumps(self.pr).encode())


def run(private):
    if os.name != "nt": raise ValueError("windows_route_required")
    if subprocess.run(["git", "status", "--porcelain"], cwd=CHECKOUT,
                      capture_output=True, check=True).stdout.strip():
        raise ValueError("source_not_clean")
    private.mkdir(parents=True, exist_ok=True)
    with (private / (IDENTITY + ".claim")).open("x") as file: file.write(IDENTITY)
    root = Path(tempfile.mkdtemp(prefix=IDENTITY + "-"))
    observation = {"identity": IDENTITY, "result": "failed", "cleanup_verified": False,
                   "source_sha": git(CHECKOUT, "rev-parse", "HEAD"),
                   "declared_model_turns": 0, "declared_real_provider_calls": 0}
    server = None
    stopped = threading.Event()
    verifier_thread = None
    agent = None
    name, launch = "laomedo-codex-" + secrets.token_hex(8), secrets.token_hex(16)
    try:
        trusted, remote, stage, runner = (root / n for n in ("trusted", "remote.git", "private", "runner"))
        trusted.mkdir(); remote.mkdir(); stage.mkdir()
        git(trusted, "init", "--quiet", "-b", "main")
        (trusted / "base.txt").write_text("baseline\n", encoding="ascii")
        git(trusted, "add", "base.txt")
        git(trusted, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "base")
        baseline = git(trusted, "rev-parse", "HEAD")
        baseline_bundle = root / "baseline.bundle"
        git(trusted, "bundle", "create", str(baseline_bundle), "refs/heads/main")
        git(remote, "init", "--bare", "--quiet")
        workspace = runner / "runs" / "run-a" / "workspace"
        workspace.parent.mkdir(parents=True)
        subprocess.run(["git", "clone", "--quiet", "--no-local", str(trusted), str(workspace)],
                       check=True, capture_output=True, env=_base_git_environment())
        git(workspace, "checkout", "--quiet", "-b", "run-branch")
        connection = {"current": True}
        fake = FakeGitHub(remote)
        push_calls = []
        def fake_git(args, **kwargs):
            revised = list(args)
            expected = "https://github.com/example/disposable.git"
            if "push" in revised:
                if revised.count(expected) != 1: raise ValueError("unexpected_git_remote")
                revised[revised.index(expected)] = str(remote)
                push_calls.append({"refspec": revised[-1]})
            return subprocess.run(revised, **kwargs)
        def credential(cid, generation):
            if (cid, generation) != (IDENTITY, 1) or not connection["current"]:
                raise KeyError("connection_invalid")
            return "synthetic-host-only-credential"
        transport = GitHubMediatedTransport(
            GitHubGitTransport(REPOSITORY, trusted, baseline, credential,
                               run=fake_git, require_verified_stage=True),
            GitHubRestTransport(REPOSITORY, credential, opener=fake))
        store = MediationStore(root / "effects.sqlite",
            verified_stage_resolver=make_grant_stage_resolver(runner, stage, runner),
            stage_freezer=make_grant_bundle_freezer(runner, stage, runner),
            verified_workflow_classifier=classify_verified_workflow,
            connection_is_current=lambda cid, gen, repo: connection["current"] and (cid, gen, repo) == (IDENTITY, 1, REPOSITORY))
        grant, token = store.issue(run_id="run-a", invocation_id="invocation-a", repository=REPOSITORY,
            branch="run-branch", operations={"git_push", "pr_create", "pr_update", "pr_read"},
            ttl_seconds=60, connection_id=IDENTITY, connection_generation=1)
        record_path = workspace.parent / "record.json"
        record = {"run_id": "run-a", "status": "running", "workspace_mode": "git",
            "git_baseline": baseline, "github_scope": {"repository": REPOSITORY, "branch": "run-branch"},
            "container_ownership": {"name": name, "launch_token": launch, "grant_id": grant,
                "supervised": True, "cleanup_verified": False}}
        record_path.write_text(json.dumps(record), encoding="utf-8")
        capability = root / "capability"
        capability.write_text(token, encoding="ascii")
        server = MediationHTTPService(store, transport)
        threading.Thread(target=server.serve, daemon=True).start()
        verifier = BundleVerifier(runner, stage, agent_mount=runner, baseline_bundle=baseline_bundle,
                                  baseline_sha256=sha256(baseline_bundle.read_bytes()).hexdigest())
        verifier_thread = threading.Thread(target=verifier.serve, args=(stopped,), daemon=True)
        verifier_thread.start()
        command = ["docker", "run", "--name", name, "--pull=never", "--network", "bridge",
                   "--label", LABEL_RUN + "=run-a", "--label", LABEL_TOKEN + "=" + launch,
                   "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                   "--user", "10001:10001", "--pids-limit", "128", "--memory", "1g",
                   "--env", "GIT_CONFIG_GLOBAL=/dev/null", "--env", "GIT_CONFIG_NOSYSTEM=1",
                   "--env", "LAOMEDO_MEDIATOR_URL=http://host.docker.internal:" + str(server.port) + "/v1/mediate",
                   "--env", "LAOMEDO_MEDIATOR_INSTANCE=" + server.instance,
                   "--env", "LAOMEDO_CAPABILITY_FILE=/run/laomedo/capability", "--workdir", "/draft"]
        for source, target, readonly in ((workspace, "/draft", False), (capability, "/run/laomedo/capability", True),
                  (CHECKOUT / "laomedo/agent_mediation_client.mjs", "/run/laomedo/mediate.mjs", True),
                  (FIXTURE, "/run/laomedo/fixture.mjs", True)):
            command.extend(["--mount", "type=bind,source=" + str(source) + ",target=" + target + (",readonly" if readonly else "")])
        command.extend([PINNED_IMAGE_ID, "node", "/run/laomedo/fixture.mjs"])
        agent = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 45
        result_file = workspace / "delivery-result.json"
        while not result_file.exists() and time.monotonic() < deadline:
            if agent.poll() is not None: raise RuntimeError("fixture_exited_early")
            time.sleep(.1)
        if not result_file.is_file(): raise RuntimeError("delivery_pending_no_retry")
        result = json.loads(result_file.read_bytes())
        state, container_id = inspect_exact(name, "run-a", launch)
        observation.update(agent_still_owned=state == "owned", agent_client_alive=agent.poll() is None,
            commit=result["commit"], number=result["number"], final_body_sha256=sha256(result["final_body"].encode()).hexdigest(),
            operations=result["operations"], push_calls=push_calls, rest_calls=list(fake.calls))
        if (state != "owned" or agent.poll() is not None or
                git(remote, "rev-parse", "refs/heads/run-branch") != result["commit"] or
                fake.pr["body"] != result["final_body"]): raise RuntimeError("delivery_readback_mismatch")
        before = len(fake.calls) + len(push_calls)
        record["status"] = "completed"
        record_path.write_text(json.dumps(record), encoding="utf-8")
        def refused(op, payload, effect=None):
            try:
                value = store.invoke(token=token, repository=REPOSITORY, operation=op,
                                     payload=payload, effect_id=effect, transport=transport)
                return value.get("state") != "confirmed"
            except MediationError: return True
        observation["completed_freeze_denied"] = refused("bundle_freeze", {"attempt_id": "late-attempt"})
        observation["completed_push_denied"] = refused("git_push", {"branch": "run-branch", "commit": result["commit"],
            "stage_attempt_id": "delivery-attempt"}, "late-push")
        connection["current"] = False
        observation["changed_connection_denied"] = refused("pr_read", {"number": 7})
        store.revoke_run("run-a")
        observation["revoked_new_write_denied"] = refused("pr_update", {"number": 7}, "revoked-update")
        observation["provider_count_unchanged_after_controls"] = before == len(fake.calls) + len(push_calls)
        if not all(observation[k] is True for k in ("completed_freeze_denied", "completed_push_denied",
             "changed_connection_denied", "revoked_new_write_denied", "provider_count_unchanged_after_controls")):
            raise RuntimeError("negative_control_failed")
        observation["result"] = "passed"
    except Exception as failure:
        observation["failure_class"] = type(failure).__name__
    finally:
        observation["cleanup_verified"], _ = cleanup_exact(name, "run-a", launch)
        if agent is not None:
            try: agent.wait(timeout=10)
            except subprocess.TimeoutExpired: agent.kill(); agent.wait(timeout=5)
        stopped.set()
        if verifier_thread: verifier_thread.join(timeout=60)
        if server: server.close()
        if not observation["cleanup_verified"]: observation["result"] = "cleanup_unverified"
        with (private / (IDENTITY + ".json")).open("x", encoding="utf-8", newline="\n") as file:
            json.dump(observation, file, sort_keys=True, indent=2); file.write("\n")
    return observation


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-state", required=True, type=Path)
    print(json.dumps(run(parser.parse_args().private_state), sort_keys=True))
