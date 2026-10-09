"""Bounded, credential-free Git-object stage for frozen run bundle bytes.

This module produces a private verified bundle; it never reads a provider
credential or pushes a ref. It requires an already frozen run-bound input
and a trusted host-supplied baseline bundle. A failed or uncertain stage is
one-shot and cannot be retried under the same attempt identity.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import time

from .bundle_ingest import (_bound_roots, _bundle_bytes, _durable_json,
                            _record, _redirected, BundleIngestError,
                            MAX_BUNDLE_BYTES, _IDENTITY)


_IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_OBJECT_ID = re.compile(rb"[0-9a-f]{40}\Z")
SCRIPT = Path(__file__).parent / "resources" / "bundle_stage.sh"
PINNED_IMAGE_ID = "sha256:eceda79a349c46a8afd6fb271e92b979f872ca67cbdf228fde6dee0856481e78"
MEMORY_BYTES = 128 * 1024 * 1024
MAX_OUTPUT_BYTES = 32 * 1024 * 1024


class BundleStageError(RuntimeError):
    """Known refusal before bounded container dispatch."""


def _single_bundle_commit(data: bytes, expected_ref: str) -> str:
    """Accept one SHA-1 ref; Git verifies prerequisite/pack integrity later."""
    end = data.find(b"\n\n")
    if end < 0 or end > 4096 or not data.startswith(b"# v"):
        raise BundleStageError("bundle_header_invalid")
    lines = data[:end].split(b"\n")
    if lines[0] not in (b"# v2 git bundle", b"# v3 git bundle"):
        raise BundleStageError("bundle_version_unsupported")
    v2 = lines[0] == b"# v2 git bundle"
    formats = [line for line in lines[1:] if line.startswith(b"@object-format=")]
    if (v2 and any(line.startswith(b"@") for line in lines[1:])) or \
            (formats and formats != [b"@object-format=sha1"]) or \
            any(line.startswith(b"@") and line != b"@object-format=sha1"
                for line in lines[1:]):
        raise BundleStageError("bundle_version_unsupported")
    for line in lines[1:]:
        if line.startswith(b"-") and not _OBJECT_ID.fullmatch(
                line[1:].split(b" ", 1)[0]):
            raise BundleStageError("bundle_header_invalid")
    refs = [line.split(b" ", 1) for line in lines[1:]
            if line and not line.startswith((b"-", b"@"))]
    if (len(refs) != 1 or len(refs[0]) != 2 or
            not _OBJECT_ID.fullmatch(refs[0][0]) or
            refs[0][1] != expected_ref.encode("ascii")):
        raise BundleStageError("bundle_ref_invalid")
    return refs[0][0].decode("ascii")


def _run(args: list[str], timeout: float = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False,
                          timeout=timeout)


def _read_frozen(runner_state: Path, private_root: Path,
                 run_id: str, attempt_id: str) -> tuple[Path, dict]:
    runner_state, private_root = _bound_roots(runner_state, private_root)
    if (not isinstance(run_id, str) or not _IDENTITY.fullmatch(run_id) or
            not isinstance(attempt_id, str) or not _IDENTITY.fullmatch(attempt_id)):
        raise BundleStageError("identity_invalid")
    _, binding = _record(runner_state, run_id)
    run_home = private_root / run_id
    attempt = run_home / attempt_id
    if (_redirected(run_home) or not run_home.is_dir() or
            run_home.resolve(strict=True).parent != private_root or
            _redirected(attempt) or not attempt.is_dir() or
            attempt.resolve(strict=True).parent != run_home):
        raise BundleStageError("frozen_attempt_unavailable")
    manifest = attempt / "result.json"
    if _redirected(manifest) or not manifest.is_file():
        raise BundleStageError("frozen_attempt_unavailable")
    try:
        with manifest.open("rb") as stream:
            raw = stream.read(256 * 1024 + 1)
        if len(raw) > 256 * 1024:
            raise BundleStageError("frozen_attempt_invalid")
        frozen = json.loads(raw)
    except (OSError, ValueError) as error:
        raise BundleStageError("frozen_attempt_invalid") from error
    if (not isinstance(frozen, dict) or frozen.get("status") != "frozen" or
            any(frozen.get(key) != value for key, value in binding.items()) or
            frozen.get("attempt_id") != attempt_id or
            not isinstance(frozen.get("bundle_sha256"), str) or
            not _SHA.fullmatch(frozen["bundle_sha256"])):
        raise BundleStageError("frozen_attempt_invalid")
    source = attempt / "input.bundle"
    try:
        payload = _bundle_bytes(source)
    except BundleIngestError as error:
        raise BundleStageError("frozen_bundle_invalid") from error
    if hashlib.sha256(payload).hexdigest() != frozen["bundle_sha256"]:
        raise BundleStageError("frozen_bundle_changed")
    frozen["advertised_commit"] = _single_bundle_commit(
        payload, "refs/heads/" + frozen["branch"])
    return attempt, frozen


def _inspect_limits(config: dict, image_id: str) -> bool:
    try:
        host = config["HostConfig"]
        binds = [mount for mount in config["Mounts"] if mount["Type"] == "bind"]
        others = [mount for mount in config["Mounts"] if mount["Type"] != "bind"]
        return (config["Image"] == image_id and host["NetworkMode"] == "none" and
                host["ReadonlyRootfs"] is True and
                host["Memory"] == MEMORY_BYTES and host["PidsLimit"] == 32 and
                all(flag in host["Tmpfs"]["/stage"] for flag in
                    ("size=32m", "nosuid", "noexec")) and
                config["Config"]["User"] == "10001:10001" and
                "ALL" in host["CapDrop"] and
                any(value.startswith("no-new-privileges") for value in
                    host["SecurityOpt"]) and
                sorted(mount["Destination"] for mount in binds) ==
                ["/baseline.bundle", "/input.bundle", "/verify.sh"] and
                all(not mount["RW"] for mount in binds) and
                all(mount["Type"] == "tmpfs" and
                    mount["Destination"] == "/stage" for mount in others))
    except (KeyError, TypeError, ValueError):
        return False


def _container_stage(attempt: Path, frozen: dict, image_id: str,
                     *, docker=_run) -> dict:
    name = "laomedo-bundle-stage-" + secrets.token_hex(8)
    result = {"status": "unknown", "exit_code": None,
              "cleanup_verified": False, "output_sha256": None,
              "output_bytes": None, "stage_markers": []}
    started = time.monotonic()
    created = False
    try:
        mounts = [(attempt / "baseline.bundle", "/baseline.bundle"),
                  (attempt / "input.bundle", "/input.bundle"),
                  (SCRIPT, "/verify.sh")]
        args = ["docker", "create", "--name", name, "--label",
                "laomedo.bundle-stage=" + name, "--pull=never", "--network", "none",
                "--read-only", "--cap-drop", "ALL", "--security-opt",
                "no-new-privileges", "--user", "10001:10001",
                "--pids-limit", "32", "--memory", "128m", "--tmpfs",
                "/stage:rw,nosuid,noexec,size=32m,mode=1777"]
        for source, target in mounts:
            args.extend(["--mount", f"type=bind,source={source},target={target},readonly"])
        args.extend([image_id, "sh", "/verify.sh", frozen["baseline"],
                     frozen["commit"]])
        created = True  # a lost create reply still gets exact-name reconciliation
        if docker(args, 30).returncode:
            result["status"] = "create_failed"
            return result
        inspected = docker(["docker", "inspect", name], 30)
        if inspected.returncode or not _inspect_limits(
                json.loads(inspected.stdout)[0], image_id):
            result["status"] = "limit_unverified"
            return result
        result["limits_verified"] = True
        if docker(["docker", "start", name], 30).returncode:
            result["status"] = "start_unknown"
            return result
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            logs = docker(["docker", "logs", "--tail", "20", name], 10)
            state = docker(["docker", "inspect", name], 10)
            if logs.returncode or state.returncode:
                return result
            lines = logs.stdout.splitlines()
            current = json.loads(state.stdout)[0]["State"]
            result["exit_code"] = current["ExitCode"]
            result["stage_markers"] = [line for line in lines
                                       if line.startswith("STAGE_FAILED=")]
            if result["stage_markers"]:
                result["status"] = "verification_failed"
                return result
            if "STAGE_VERIFIED" in lines:
                if current["Running"] is not True:
                    result["status"] = "output_unavailable"
                    return result
                break
            if current["Running"] is not True:
                result["status"] = "verification_failed"
                return result
            time.sleep(.1)
        else:
            result["status"] = "stage_timeout"
            return result
        pending = attempt / "verified.bundle.pending"
        if pending.exists() or (attempt / "verified.bundle").exists():
            result["status"] = "output_conflict"
            return result
        copied = docker(["docker", "cp", name + ":/stage/verified.bundle",
                         str(pending)], 30)
        if copied.returncode:
            result["status"] = "output_unavailable"
            return result
        metadata = pending.lstat()
        if (_redirected(pending) or not stat.S_ISREG(metadata.st_mode) or
                metadata.st_nlink != 1 or metadata.st_size > MAX_OUTPUT_BYTES):
            result["status"] = "output_invalid"
            return result
        with pending.open("rb") as source:
            payload = source.read(MAX_OUTPUT_BYTES + 1)
        if len(payload) != metadata.st_size or len(payload) > MAX_OUTPUT_BYTES:
            result["status"] = "output_invalid"
            return result
        try:
            exported_commit = _single_bundle_commit(payload,
                                                     "refs/heads/validated")
        except BundleStageError:
            result["status"] = "output_invalid"
            return result
        if exported_commit != frozen["commit"]:
            result["status"] = "output_invalid"
            return result
        with pending.open("rb+") as source:
            os.fsync(source.fileno())
        os.replace(pending, attempt / "verified.bundle")
        result.update(status="verified", output_sha256=hashlib.sha256(
            payload).hexdigest(), output_bytes=len(payload))
        return result
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, IndexError):
        return result
    finally:
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        if created:
            try:
                inspected = docker(["docker", "inspect", name], 30)
                if inspected.returncode == 0:
                    found = json.loads(inspected.stdout)[0]
                    if found.get("Config", {}).get("Labels", {}).get(
                            "laomedo.bundle-stage") == name:
                        removed = docker(["docker", "rm", "--force", name], 30)
                        result["cleanup_verified"] = (removed.returncode == 0 and
                            docker(["docker", "inspect", name], 30).returncode != 0)
            except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, IndexError):
                result["cleanup_verified"] = False
        if not result["cleanup_verified"] and result["status"] == "verified":
            result["status"] = "unknown"


def verify_frozen_bundle(runner_state: Path, private_root: Path, *,
                         run_id: str, attempt_id: str,
                         baseline_bundle: Path, expected_baseline_sha256: str,
                         commit: str, image_id: str, docker=_run) -> dict:
    """One-shot verify/export from already frozen bytes; no provider write."""
    if (not isinstance(image_id, str) or not _IMAGE.fullmatch(image_id) or
            image_id != PINNED_IMAGE_ID or
            not isinstance(commit, str) or not _COMMIT.fullmatch(commit) or
            not isinstance(expected_baseline_sha256, str) or
            not _SHA.fullmatch(expected_baseline_sha256)):
        raise BundleStageError("stage_identity_invalid")
    attempt, frozen = _read_frozen(Path(runner_state), Path(private_root),
                                    run_id, attempt_id)
    if commit != frozen["advertised_commit"]:
        raise BundleStageError("candidate_commit_mismatch")
    if (attempt / "verification.json").exists() or \
            (attempt / "verification.json.pending").exists():
        raise BundleStageError("verification_identity_consumed")
    baseline_bundle = Path(baseline_bundle)
    try:
        baseline_bytes = _bundle_bytes(baseline_bundle)
    except BundleIngestError as error:
        raise BundleStageError("baseline_bundle_invalid") from error
    if hashlib.sha256(baseline_bytes).hexdigest() != expected_baseline_sha256:
        raise BundleStageError("baseline_bundle_changed")
    frozen["commit"] = commit
    result = {"run_id": run_id, "attempt_id": attempt_id,
              "status": "unknown", "source_bundle_sha256": frozen["bundle_sha256"],
              "baseline_bundle_sha256": expected_baseline_sha256,
              "baseline": frozen["baseline"], "commit": commit,
              "image_id": image_id, "policy_approved": False}
    journal = attempt / "verification.json"
    _durable_json(journal, result)
    try:
        destination = attempt / "baseline.bundle"
        with destination.open("xb") as output:
            output.write(baseline_bytes)
            output.flush()
            os.fsync(output.fileno())
        result["container"] = _container_stage(attempt, frozen, image_id,
                                               docker=docker)
        if (result["container"]["status"] == "verified" and
                result["container"]["cleanup_verified"]):
            result["status"] = "verified"
        elif (not result["container"]["cleanup_verified"] or
              result["container"]["status"] == "unknown"):
            result["status"] = "unknown"
        else:
            result["status"] = "failed"
    except Exception as error:
        result["status"] = "unknown"
        result["error_class"] = type(error).__name__
    _durable_json(journal, result)
    return result
