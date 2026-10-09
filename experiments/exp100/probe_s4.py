"""One-shot, no-credential Docker resource-boundary experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time

from experiments.exp100.bundle_transfer import git


ROOT = Path(__file__).resolve().parents[2]
OBSERVATION = Path(__file__).with_name("observation-s4.json")
SCRIPT = Path(__file__).with_name("verify_s4.sh")
IMAGE_ID = "sha256:eceda79a349c46a8afd6fb271e92b979f872ca67cbdf228fde6dee0856481e78"
IDENTITY = "EXP-100-S4-01"
MEMORY_BYTES = 128 * 1024 * 1024


def _run(args: list[str], *, timeout: float = 30,
         cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                          cwd=cwd, check=False)


def _git(*args: str) -> str:
    result = git(list(args))
    if result.returncode:
        raise RuntimeError("fixture_git_failed")
    return result.stdout.decode("utf-8").strip()


def _fixture(root: Path) -> tuple[Path, Path, str, str]:
    trusted, agent, bundle = root / "trusted", root / "agent", root / "input.bundle"
    trusted.mkdir()
    _git("init", "--quiet", str(trusted))
    (trusted / "source.txt").write_text("baseline\n", encoding="utf-8")
    _git("-C", str(trusted), "add", "source.txt")
    _git("-C", str(trusted), "-c", "user.name=Fixture", "-c",
         "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "baseline")
    baseline = _git("-C", str(trusted), "rev-parse", "HEAD")
    _git("clone", "--quiet", "--no-local", str(trusted), str(agent))
    _git("-C", str(agent), "checkout", "--quiet", "-b", "run-s4")
    (agent / "agent.txt").write_text("agent commit\n", encoding="utf-8")
    _git("-C", str(agent), "add", "agent.txt")
    _git("-C", str(agent), "-c", "user.name=Agent", "-c",
         "user.email=agent@example.invalid", "commit", "--quiet", "-m", "agent")
    commit = _git("-C", str(agent), "rev-parse", "HEAD")
    _git("-C", str(agent), "bundle", "create", str(bundle), "refs/heads/run-s4")
    if bundle.stat().st_size > 4 * 1024 * 1024:
        raise RuntimeError("fixture_bundle_oversized")
    return trusted, bundle, baseline, commit


def _docker_case(label: str, command: list[str], mounts: list[Path]) -> dict:
    name = "laomedo-s4-" + secrets.token_hex(8)
    started = time.monotonic()
    created = False
    result = {"case": label, "status": "unknown", "exit_code": None,
              "cleanup_verified": False}
    try:
        args = ["docker", "create", "--name", name, "--label",
                "laomedo.experiment=s4", "--pull=never", "--network", "none",
                "--read-only", "--cap-drop", "ALL", "--security-opt",
                "no-new-privileges", "--user", "10001:10001", "--pids-limit",
                "32", "--memory", "128m", "--tmpfs",
                "/stage:rw,nosuid,noexec,size=32m,mode=1777"]
        if mounts:
            args.extend(["--mount", f"type=bind,source={mounts[0]},target=/trusted,readonly",
                         "--mount", f"type=bind,source={mounts[1]},target=/input.bundle,readonly",
                         "--mount", f"type=bind,source={SCRIPT},target=/verify.sh,readonly"])
        args.extend([IMAGE_ID, *command])
        created = True  # reconcile the exact label even if create loses its reply
        response = _run(args)
        if response.returncode:
            result["status"] = "create_failed"
            return result
        inspected = _run(["docker", "inspect", name])
        if inspected.returncode:
            result["status"] = "inspect_failed"
            return result
        config = json.loads(inspected.stdout)[0]
        host = config["HostConfig"]
        limits = {"image_id": config["Image"],
                  "network_mode": host["NetworkMode"],
                  "read_only": host["ReadonlyRootfs"],
                  "memory_bytes": host["Memory"],
                  "pids_limit": host["PidsLimit"],
                  "tmpfs_stage": host["Tmpfs"].get("/stage")}
        result["inspected_limits"] = limits
        if (limits["image_id"] != IMAGE_ID or limits["network_mode"] != "none" or
                limits["read_only"] is not True or
                limits["memory_bytes"] != MEMORY_BYTES or
                limits["pids_limit"] != 32 or
                not limits["tmpfs_stage"] or "size=32m" not in limits["tmpfs_stage"]):
            result["status"] = "limit_mismatch"
            return result
        called = _run(["docker", "start", "--attach", name], timeout=40)
        finished = _run(["docker", "inspect", name])
        if finished.returncode:
            result["status"] = "exit_inspect_failed"
            return result
        state = json.loads(finished.stdout)[0]["State"]
        result["exit_code"] = state["ExitCode"]
        result["marker"] = next((line for line in called.stdout.splitlines()
                                 if line.startswith("S4_")), None)
        result["container_git_version"] = next((line.partition("=")[2]
            for line in called.stdout.splitlines()
            if line.startswith("S4_GIT_VERSION=")), None)
        if label == "valid_import":
            result["marker"] = ("S4_VERIFIED" if "S4_VERIFIED" in
                                called.stdout.splitlines() else None)
        result["status"] = "completed" if called.returncode == 0 else "start_unknown"
        return result
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, IndexError):
        result["status"] = "control_unknown"
        return result
    finally:
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        if created:
            inspected = _run(["docker", "inspect", name])
            if inspected.returncode == 0:
                found = json.loads(inspected.stdout)[0]
                if found.get("Config", {}).get("Labels", {}).get(
                        "laomedo.experiment") == "s4":
                    removed = _run(["docker", "rm", "--force", name])
                    result["cleanup_verified"] = removed.returncode == 0 and \
                        _run(["docker", "inspect", name]).returncode != 0


def run() -> dict:
    version = _run(["git", "--version"])
    if version.returncode:
        raise RuntimeError("host_git_unavailable")
    image = _run(["docker", "image", "inspect", IMAGE_ID,
                  "--format", "{{.Id}}"])
    if image.returncode or image.stdout.strip() != IMAGE_ID:
        raise RuntimeError("pinned_image_unavailable")
    with tempfile.TemporaryDirectory(prefix="laomedo-s4-") as directory:
        root = Path(directory)
        trusted, bundle, baseline, commit = _fixture(root)
        trusted_hash_before = hashlib.sha256((trusted / "source.txt").read_bytes()).hexdigest()
        bundle_hash_before = hashlib.sha256(bundle.read_bytes()).hexdigest()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            positive = _docker_case("valid_import",
                                    ["sh", "/verify.sh", baseline, commit],
                                    [trusted, bundle])
            disk = _docker_case("tmpfs_quota",
                                ["sh", "-c", "dd if=/dev/zero of=/stage/fill "
                                 "bs=1M count=40 2>/stage/dd.err && exit 91; "
                                 "grep -q 'No space left on device' /stage/dd.err "
                                 "&& echo S4_DISK_LIMIT"], [])
            script = ("const net=require('net');const s=net.createConnection({"
                      "host:'host.docker.internal',port:" + str(port) + "});"
                      "s.on('connect',()=>process.exit(91));"
                      "s.on('error',()=>{console.log('S4_NET_DENIED');process.exit(0)});"
                      "setTimeout(()=>process.exit(92),3000);")
            network = _docker_case("network_none", ["node", "-e", script], [])
            listener.settimeout(0.1)
            try:
                connection, _ = listener.accept()
                connection.close()
                reached_listener = True
            except socket.timeout:
                reached_listener = False
        cases = [positive, disk, network]
        source_unchanged = hashlib.sha256(
            (trusted / "source.txt").read_bytes()).hexdigest() == trusted_hash_before
        bundle_unchanged = hashlib.sha256(bundle.read_bytes()).hexdigest() == bundle_hash_before
        passed = (all(case["status"] == "completed" and case["exit_code"] == 0 and
                      case["cleanup_verified"] for case in cases) and
                  positive["marker"] == "S4_VERIFIED" and
                  disk["marker"] == "S4_DISK_LIMIT" and
                  network["marker"] == "S4_NET_DENIED" and not reached_listener and
                  source_unchanged and bundle_unchanged and
                  bool(positive["container_git_version"]))
        return {"schema_version": 1, "identity": IDENTITY,
                "status": "passed" if passed else "failed",
                "source_commit": _git("-C", str(ROOT), "rev-parse", "HEAD"),
                "host_git_version": version.stdout.strip(),
                "image_id": IMAGE_ID,
                "protocol_sha256": hashlib.sha256(
                    (ROOT / "experiments/exp100/PROTOCOL-04.md").read_bytes()).hexdigest(),
                "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "script_sha256": hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
                "bundle_sha256": bundle_hash_before,
                "baseline": baseline, "commit": commit,
                "cases": cases, "host_listener_reached": reached_listener,
                "trusted_source_unchanged": source_unchanged,
                "bundle_unchanged": bundle_unchanged,
                "provider_calls": 0, "model_turns": 0,
                "count_scope": "no provider/model component instantiated; no packet capture"}


def record_once(path: Path, source_commit: str) -> dict:
    with path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps({"identity": IDENTITY, "status": "unknown",
                                 "source_commit": source_commit}) + "\n")
        output.flush()
        os.fsync(output.fileno())
    try:
        observation = run()
    except Exception as error:
        observation = {"schema_version": 1, "identity": IDENTITY,
                       "status": "failed", "source_commit": source_commit,
                       "error_class": type(error).__name__}
    pending = path.with_suffix(".pending")
    with pending.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(observation, indent=2, sort_keys=True) + "\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(pending, path)
    return observation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    if not args.record:
        raise SystemExit("S4 probe requires --record; no untracked Docker dry-run")
    if OBSERVATION.exists():
        raise SystemExit("S4 evidence identity already consumed")
    status = _run(["git", "status", "--porcelain=v1", "--untracked-files=all"],
                  cwd=ROOT)
    if status.returncode or status.stdout:
        raise SystemExit("source tree must be clean before recording")
    source_commit = _git("-C", str(ROOT), "rev-parse", "HEAD")
    observation = record_once(OBSERVATION, source_commit)
    if observation.get("status") != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
