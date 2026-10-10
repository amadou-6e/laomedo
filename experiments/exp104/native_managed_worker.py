"""S12 scripted runner fixture; real lease registration, zero model turns.

Not a product runner or a capture entry point. The reviewed controller must
prepare/bind the trusted scope and paths before starting this process.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import threading
import time

from experiments.exp104.native_managed_checks import BASELINE, IDENTITY, REPOSITORY
from laomedo.agent_cli import prepare_commands
from laomedo.container_lease import cleanup_exact, inspect_exact, LABEL_RUN, LABEL_TOKEN
from laomedo.github_git_transport import _base_git_environment
from laomedo.lease_service import LeaseClient
from laomedo.local_runner import GIT_IMAGE_ID

CHECKOUT = Path(__file__).resolve().parents[2]


def identities(side):
    if side not in ("a", "b"):
        raise ValueError("invalid_side")
    return {"run_id": IDENTITY + "-run-" + side,
        "name": "laomedo-" + IDENTITY + "-" + side,
        "token": IDENTITY + "-lease-" + side,
        "branch": IDENTITY + "-" + side,
        "invocation_id": IDENTITY + "-invocation-" + side}


def command(root, side, lease, mediator):
    """Frozen owned mount surface; no token file or arbitrary container args."""
    selected = identities(side)
    workspace = root / "runner" / "runs" / selected["run_id"] / "workspace"
    wrappers = prepare_commands(workspace.parent, REPOSITORY, selected["branch"])
    args = ["docker", "run", "--name", selected["name"], "--pull=never",
        "--network=bridge", "--label", LABEL_RUN + "=" + selected["run_id"],
        "--label", LABEL_TOKEN + "=" + selected["token"], "--read-only",
        "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user=10001:10001",
        "--pids-limit=128", "--memory=1g", "--tmpfs=/tmp:rw,noexec,nosuid,size=64m",
        "--env=GIT_CONFIG_GLOBAL=/dev/null", "--env=GIT_CONFIG_NOSYSTEM=1",
        "--env=PATH=/run/laomedo/bin:/usr/local/bin:/usr/bin:/bin",
        "--env=LAOMEDO_REPOSITORY=" + REPOSITORY,
        "--env=LAOMEDO_RUN_BRANCH=" + selected["branch"], "--env=LAOMEDO_BASE_BRANCH=main",
        "--env=LAOMEDO_MEDIATOR_URL=http://host.docker.internal:" +
        str(mediator["port"]) + "/v1/mediate",
        "--env=LAOMEDO_MEDIATOR_INSTANCE=" + mediator["instance"],
        "--env=LAOMEDO_CAPABILITY_FILE=/run/laomedo/capability", "--workdir=/draft"]
    for source, target, readonly in (
            (workspace, "/draft", False), (lease.dir / "grant.secret", "/run/laomedo/capability", True),
            (wrappers, "/run/laomedo/bin", True),
            (CHECKOUT / "laomedo/agent_mediation_client.mjs", "/run/laomedo/mediate.mjs", True),
            (CHECKOUT / "laomedo/agent_gh_adapter.mjs", "/run/laomedo/gh.mjs", True),
            (CHECKOUT / "laomedo/agent_git_remote.mjs", "/run/laomedo/git-remote.mjs", True)):
        args.extend(["--mount", "type=bind,source=" + str(source) + ",target=" + target +
                     (",readonly" if readonly else "")])
    return args + [GIT_IMAGE_ID, "sh", "-c", "sleep 600"]


def run(root, side):
    selected = identities(side)
    scope = {"invocation_id": selected["invocation_id"], "repository": REPOSITORY,
             "branch": selected["branch"], "base_branch": "main"}
    lease = LeaseClient(root / "host" / "lease", run_id=selected["run_id"],
        name=selected["name"], token=selected["token"], cancelled=threading.Event(),
        mediation_request=scope)
    mediator = json.loads((root / "host/mediator/mediator.json").read_bytes())
    if (mediator.get("repository") != REPOSITORY or
            mediator.get("connection_id") != IDENTITY + "-connection" or
            mediator.get("generation") != 1):
        raise ValueError("mediator_identity_mismatch")
    record_path = root / "runner/runs" / selected["run_id"] / "record.json"
    record = {"run_id": selected["run_id"], "status": "running", "workspace_mode": "git",
        "git_baseline": BASELINE, "github_scope": scope,
        "container_ownership": {"name": selected["name"], "launch_token": selected["token"],
            "grant_id": lease.grant_id, "supervised": True, "cleanup_verified": False}}
    record_path.write_text(json.dumps(record), encoding="utf-8", newline="\n")
    child = None
    try:
        child = subprocess.Popen(command(root, side, lease, mediator),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=_base_git_environment())
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            state, metadata = inspect_exact(selected["name"], selected["run_id"], selected["token"])
            if state == "owned":
                ready = {"pid": os.getpid(), "run_id": selected["run_id"],
                         "grant_id": lease.grant_id, "container_id": metadata}
                (root / (side + "-ready.json")).write_text(json.dumps(ready),
                    encoding="utf-8", newline="\n")
                break
            if child.poll() is not None or lease.lost.is_set():
                raise RuntimeError("scripted_container_unavailable")
            time.sleep(.1)
        else:
            raise RuntimeError("scripted_container_not_ready")
        deadline = time.monotonic() + 600
        while child.poll() is None and time.monotonic() < deadline:
            if lease.lost.is_set():
                raise RuntimeError("lease_service_lost")
            time.sleep(.2)
        if child.poll() is None:
            raise RuntimeError("scripted_container_deadline")
    finally:
        verified, _ = cleanup_exact(selected["name"], selected["run_id"], selected["token"])
        if child is not None:
            child.wait(timeout=10)
        record["status"] = "completed" if verified else "interrupted"
        record["container_ownership"]["cleanup_verified"] = verified
        record_path.write_text(json.dumps(record), encoding="utf-8", newline="\n")
        lease.finish()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--side", required=True, choices=("a", "b"))
    args = parser.parse_args()
    try:
        run(args.root.resolve(), args.side)
    except Exception as failure:
        # Never emit raw paths, lease capabilities or provider diagnostics.
        print(json.dumps({"status": "fixture_failed", "error_class": type(failure).__name__}))
        raise SystemExit(1)
