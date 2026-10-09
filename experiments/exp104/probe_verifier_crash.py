"""Single-use credential-free verifier-loss diagnostic; frozen protocol peer."""
from hashlib import sha256
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

CHECKOUT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CHECKOUT))
from laomedo.bundle_ingest import HANDOFF_NAME, freeze_run_bundle
from laomedo.bundle_stage import PINNED_IMAGE_ID, verify_frozen_bundle
from laomedo.bundle_verifier import BundleVerifier
from laomedo.bundle_stage_ownership import _inspect
from laomedo.github_git_transport import _base_git_environment

IDENTITY = "exp104-verifier-loss-s2-20261009"


def docker(*args):
    return subprocess.run(["docker", *args], capture_output=True,
                          text=True, timeout=20)


def git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], check=True,
                          capture_output=True, env=_base_git_environment()).stdout.decode().strip()


def worker(root):
    config = json.loads((root / "config.json").read_bytes())
    def paused_export(*_args):
        (root / "ready").write_text("before-export\n", encoding="ascii")
        time.sleep(120)
        raise RuntimeError("pause_deadline_expired")
    def verify(*args, **kwargs):
        return verify_frozen_bundle(*args, **kwargs, export=paused_export)
    instance = BundleVerifier(root / "runner", root / "private",
        agent_mount=root / "runner", baseline_bundle=root / "baseline.bundle",
        baseline_sha256=config["baseline_hash"], verify=verify)
    instance.scan_once()


def run(private):
    if os.name != "nt":
        raise ValueError("windows_required")
    if subprocess.run(["git", "status", "--porcelain"], cwd=CHECKOUT,
                      capture_output=True, check=True).stdout.strip():
        raise ValueError("source_not_clean")
    private.mkdir(parents=True, exist_ok=True)
    with (private / (IDENTITY + ".claim")).open("x") as file:
        file.write(IDENTITY)
    root = Path(tempfile.mkdtemp(prefix=IDENTITY + "-"))
    observed = {"identity": IDENTITY, "result": "failed",
                "source_sha": git(CHECKOUT, "rev-parse", "HEAD"),
                "cleanup": {}, "declared_model_turns": 0,
                "declared_provider_operations": 0}
    child = None
    owner = None
    control_name = "laomedo-bundle-stage-" + os.urandom(8).hex()
    try:
        trusted = root / "trusted"
        trusted.mkdir()
        git(trusted, "init", "--quiet")
        (trusted / "base.txt").write_text("baseline\n", encoding="ascii")
        git(trusted, "add", "base.txt")
        git(trusted, "-c", "user.name=Probe", "-c", "user.email=probe@example.invalid",
            "commit", "--quiet", "-m", "baseline")
        baseline = git(trusted, "rev-parse", "HEAD")
        git(trusted, "bundle", "create", str(root / "baseline.bundle"), "HEAD")
        workspace = root / "runner" / "runs" / "run-a" / "workspace"
        workspace.parent.mkdir(parents=True)
        subprocess.run(["git", "clone", "--quiet", "--no-local", str(trusted), str(workspace)],
                       check=True, capture_output=True, env=_base_git_environment())
        git(workspace, "checkout", "--quiet", "-b", "run-branch")
        (workspace / "change.txt").write_text("candidate\n", encoding="ascii")
        git(workspace, "add", "change.txt")
        git(workspace, "-c", "user.name=Probe", "-c", "user.email=probe@example.invalid",
            "commit", "--quiet", "-m", "candidate")
        commit = git(workspace, "rev-parse", "HEAD")
        git(workspace, "bundle", "create", str(workspace / HANDOFF_NAME), "refs/heads/run-branch")
        record = {"run_id": "run-a", "status": "running", "workspace_mode": "git",
                  "git_baseline": baseline, "github_scope": {
                      "repository": "example/disposable", "branch": "run-branch"},
                  "container_ownership": {"name": "synthetic-agent", "launch_token": "synthetic",
                      "grant_id": "synthetic-grant", "supervised": True, "cleanup_verified": False}}
        (workspace.parent / "record.json").write_text(json.dumps(record), encoding="utf-8")
        (root / "private").mkdir()
        baseline_hash = sha256((root / "baseline.bundle").read_bytes()).hexdigest()
        (root / "config.json").write_text(json.dumps({"baseline_hash": baseline_hash}))
        freeze_run_bundle(root / "runner", root / "private", run_id="run-a", attempt_id="attempt-a")
        attempt = root / "private" / "run-a" / "attempt-a"
        observed.update(baseline=baseline, commit=commit, baseline_bundle_sha256=baseline_hash,
                        input_bundle_sha256=sha256((attempt / "input.bundle").read_bytes()).hexdigest())
        made = docker("create", "--name", control_name, "--label", "laomedo.probe=" + IDENTITY,
                      "--pull=never", "--network", "none", "--read-only", "--cap-drop", "ALL",
                      "--security-opt", "no-new-privileges", "--user", "10001:10001",
                      "--pids-limit", "32", "--memory", "128m", PINNED_IMAGE_ID, "sh", "-c", "sleep 120")
        if made.returncode or docker("start", control_name).returncode:
            raise RuntimeError("control_start_failed")
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--child", str(root)],
                                 cwd=CHECKOUT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline and not (root / "ready").exists():
            if child.poll() is not None:
                raise RuntimeError("worker_exited_before_pause")
            time.sleep(.1)
        if not (root / "ready").exists():
            raise RuntimeError("worker_readiness_timeout")
        owner = json.loads((attempt / "container-owner.json").read_bytes())
        observed["reservation_present_before_kill"] = True
        subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                       capture_output=True, check=True, timeout=10)
        child.wait(timeout=5)
        adapter = lambda args, timeout: subprocess.run(args, capture_output=True,
                                                      text=True, timeout=timeout)
        state, stage_id = _inspect(owner, adapter)
        if state != "owned":
            raise RuntimeError("orphan_not_observed")
        observed["stage_before"] = {"state": state, "id": stage_id}
        instance = BundleVerifier(root / "runner", root / "private", agent_mount=root / "runner",
                                  baseline_bundle=root / "baseline.bundle", baseline_sha256=baseline_hash)
        dispatched = instance.scan_once()
        observed["restarted_scan_dispatches"] = dispatched
        observed["orphan_cleanup"] = json.loads((attempt / "orphan-cleanup.json").read_bytes())
        observed["verification_status"] = json.loads((attempt / "verification.json").read_bytes())["status"]
        observed["claim_preserved"] = (attempt / "verifier-claim.json").is_file()
        observed["stage_after"] = _inspect(owner, adapter)[0]
        control = json.loads(docker("inspect", control_name).stdout)[0]
        observed["control_still_running"] = control["State"]["Running"]
        if (dispatched or observed["verification_status"] != "unknown" or
                not observed["claim_preserved"] or observed["stage_after"] != "absent" or
                observed["orphan_cleanup"].get("cleanup_verified") is not True or
                not observed["control_still_running"]):
            raise RuntimeError("orphan_cleanup_assertion_failed")
        observed["result"] = "passed"
    except Exception as failure:
        observed["failure_class"] = type(failure).__name__
    finally:
        if child is not None and child.poll() is None:
            subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True, timeout=10)
            child.wait(timeout=5)
        # Recover reservation even if the worker died before readiness.
        reservation = root / "private" / "run-a" / "attempt-a" / "container-owner.json"
        if owner is None and reservation.is_file():
            owner = json.loads(reservation.read_bytes())
        for kind, name in (("control", control_name), ("stage", owner["name"] if owner else None)):
            if name is None:
                continue
            try:
                response = docker("inspect", name)
                if response.returncode and "No such object:" in response.stderr:
                    observed["cleanup"][kind] = True
                    continue
                entry = json.loads(response.stdout)[0]
                labels = entry["Config"]["Labels"] or {}
                if ((kind == "control" and labels.get("laomedo.probe") != IDENTITY) or
                        (kind == "stage" and (labels.get("laomedo.bundle-stage-token") != owner["token"] or
                                               entry["Image"] != owner["image_id"]))):
                    raise RuntimeError("cleanup_ownership_changed")
                removed = docker("rm", "--force", entry["Id"])
                after = docker("inspect", name)
                observed["cleanup"][kind] = removed.returncode == 0 and after.returncode != 0 and "No such object:" in after.stderr
            except Exception:
                observed["cleanup"][kind] = False
        if any(value is not True for value in observed["cleanup"].values()):
            observed["result"] = "cleanup_unverified"
        with (private / (IDENTITY + ".json")).open("x", encoding="utf-8", newline="\n") as file:
            json.dump(observed, file, sort_keys=True, indent=2)
            file.write("\n")
    return observed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-state", type=Path)
    parser.add_argument("--child", type=Path)
    args = parser.parse_args()
    if args.child:
        worker(args.child)
    elif args.private_state:
        print(json.dumps(run(args.private_state), sort_keys=True))
    else:
        parser.error("select parent or child mode")
