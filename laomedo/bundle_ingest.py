"""Freeze a run-bound Git bundle without trusting an agent-selected host path.

This is the credential-free ingress half of mediated Git delivery. It does
not verify Git objects, stage a commit, push, or grant provider authority.
The caller supplies only a trusted runner state root and a private stage root;
the handoff file name and run workspace location are fixed here.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat


MAX_BUNDLE_BYTES = 4 * 1024 * 1024
MAX_RECORD_BYTES = 256 * 1024
HANDOFF_NAME = ".laomedo-handoff.bundle"
_IDENTITY = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_BRANCH = re.compile(r"[A-Za-z0-9._/-]+\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


class BundleIngestError(RuntimeError):
    """Typed refusal before a bundle becomes a trusted staged commit."""


def _redirected(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return True
    return path.is_symlink() or bool(
        getattr(metadata, "st_file_attributes", 0) &
        getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _outside_git(path: Path) -> bool:
    return not any((parent / ".git").exists() for parent in
                   (path, *path.parents))


def _bound_roots(runner_state: Path, private_root: Path) -> tuple[Path, Path]:
    if (_redirected(runner_state) or _redirected(private_root) or
            not runner_state.is_dir() or not private_root.is_dir()):
        raise BundleIngestError("stage_boundary_invalid")
    runner_state = runner_state.resolve(strict=True)
    private_root = private_root.resolve(strict=True)
    if (not _outside_git(runner_state) or not _outside_git(private_root) or
            private_root == runner_state or
            private_root.is_relative_to(runner_state) or
            runner_state.is_relative_to(private_root)):
        raise BundleIngestError("stage_boundary_invalid")
    return runner_state, private_root


def _record(runner_state: Path, run_id: str) -> tuple[Path, dict]:
    if not isinstance(run_id, str) or not _IDENTITY.fullmatch(run_id):
        raise BundleIngestError("run_identity_invalid")
    run_dir = runner_state / "runs" / run_id
    if (_redirected(runner_state / "runs") or
            _redirected(run_dir) or not run_dir.is_dir() or
            run_dir.resolve(strict=True).parent !=
            (runner_state / "runs").resolve(strict=True)):
        raise BundleIngestError("run_binding_invalid")
    source = run_dir / "record.json"
    if _redirected(source) or not source.is_file():
        raise BundleIngestError("run_binding_invalid")
    try:
        with source.open("rb") as stream:
            record_bytes = stream.read(MAX_RECORD_BYTES + 1)
        if len(record_bytes) > MAX_RECORD_BYTES:
            raise BundleIngestError("run_binding_invalid")
        record = json.loads(record_bytes)
    except (OSError, ValueError) as error:
        raise BundleIngestError("run_binding_invalid") from error
    if not isinstance(record, dict):
        raise BundleIngestError("run_binding_invalid")
    scope = record.get("github_scope") or {}
    if not isinstance(scope, dict):
        raise BundleIngestError("run_binding_invalid")
    branch = scope.get("branch")
    repository = scope.get("repository")
    baseline = record.get("git_baseline")
    status = record.get("status")
    if (record.get("run_id") != run_id or
            (status != "running" and status != "completed") or
            record.get("workspace_mode") != "git" or
            not isinstance(branch, str) or not _BRANCH.fullmatch(branch) or
            branch.startswith("/") or ".." in branch or
            not isinstance(repository, str) or
            not _REPOSITORY.fullmatch(repository) or
            not isinstance(baseline, str) or not _SHA.fullmatch(baseline)):
        raise BundleIngestError("run_binding_invalid")
    workspace = run_dir / "workspace"
    if (_redirected(workspace) or not workspace.is_dir() or
            workspace.resolve(strict=True).parent != run_dir.resolve(strict=True)):
        raise BundleIngestError("run_binding_invalid")
    binding = {"run_id": run_id, "repository": repository,
               "branch": branch, "baseline": baseline}
    if status == "running":
        # record.json gains thread, turn and credential observations during a
        # live invocation. Bind only the host-owned launch/lease identity;
        # the mediator separately rechecks that this grant is still valid.
        owner = record.get("container_ownership")
        if (not isinstance(owner, dict) or owner.get("supervised") is not True or
                owner.get("cleanup_verified") is not False or
                any(not isinstance(owner.get(key), str) or
                    not _IDENTITY.fullmatch(owner[key]) for key in
                    ("name", "launch_token", "grant_id"))):
            raise BundleIngestError("run_binding_invalid")
        stable = {**binding, "workspace_mode": "git",
                  "grant_id": owner["grant_id"],
                  "launch_token": owner["launch_token"],
                  "container_name": owner["name"]}
        encoded = json.dumps(stable, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        binding.update(binding_mode="active", grant_id=owner["grant_id"],
                       run_binding_sha256=hashlib.sha256(encoded).hexdigest())
    else:
        # Preserve the completed-record format of the earlier local probes.
        binding["run_record_sha256"] = hashlib.sha256(record_bytes).hexdigest()
    return run_dir, binding


def _bundle_bytes(path: Path) -> bytes:
    if _redirected(path) or not path.is_file():
        raise BundleIngestError("bundle_not_regular")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as source:
            before = os.fstat(source.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or
                    before.st_size > MAX_BUNDLE_BYTES):
                raise BundleIngestError("bundle_size_or_type")
            payload = source.read(MAX_BUNDLE_BYTES + 1)
            after = os.fstat(source.fileno())
            current = path.lstat()
            if (len(payload) != before.st_size or len(payload) > MAX_BUNDLE_BYTES or
                    (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) or
                    (before.st_dev, before.st_ino) !=
                    (current.st_dev, current.st_ino) or _redirected(path)):
                raise BundleIngestError("bundle_changed_or_oversized")
            return payload
    except OSError as error:
        raise BundleIngestError("bundle_unreadable") from error


def _durable_json(path: Path, value: dict) -> None:
    pending = path.with_name(path.name + ".pending")
    with pending.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(value, sort_keys=True) + "\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(pending, path)
    if os.name != "nt":
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _require_reconciled_prior_attempts(run_home: Path, prior_attempt_authorizer=None) -> None:
    """Never let an unverified or unknown freeze be superseded silently."""
    for prior in run_home.iterdir():
        if _redirected(prior) or not prior.is_dir():
            raise BundleIngestError("attempt_unreconciled")
        outcome = prior / "result.json"
        if _redirected(outcome) or not outcome.is_file():
            raise BundleIngestError("attempt_unreconciled")
        try:
            with outcome.open("rb") as stream:
                raw = stream.read(MAX_RECORD_BYTES + 1)
            if len(raw) > MAX_RECORD_BYTES:
                raise BundleIngestError("attempt_unreconciled")
            result = json.loads(raw)
        except (OSError, ValueError) as error:
            raise BundleIngestError("attempt_unreconciled") from error
        if isinstance(result, dict) and result.get("status") == "frozen" and prior_attempt_authorizer is not None:
            try:
                authorized = prior_attempt_authorizer(prior.name) is True
            except Exception:
                authorized = False
            if authorized:
                continue
        if (not isinstance(result, dict) or result.get("status") != "refused" or
                (prior / "input.bundle").exists()):
            raise BundleIngestError("attempt_unreconciled")


def freeze_run_bundle(runner_state: Path, private_root: Path, *, run_id: str,
                      attempt_id: str, prior_attempt_authorizer=None) -> dict:
    """Save exact agent bytes under a host-private, one-shot run identity.

    A returned ``frozen`` status is **not** Git verification or push approval.
    The host may later verify the immutable private file in a bounded stage.
    A crash leaves an attempt or lock that must be reconciled, never replayed.
    """
    runner_state, private_root = _bound_roots(Path(runner_state),
                                               Path(private_root))
    run_dir, binding = _record(runner_state, run_id)
    if not isinstance(attempt_id, str) or not _IDENTITY.fullmatch(attempt_id):
        raise BundleIngestError("attempt_identity_invalid")
    run_home = private_root / run_id
    run_home.mkdir(mode=0o700, exist_ok=True)
    if _redirected(run_home):
        raise BundleIngestError("stage_boundary_invalid")
    lock = private_root / (run_id + ".lock")
    try:
        with lock.open("x", encoding="ascii") as output:
            output.write(attempt_id + "\n")
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError as error:
        raise BundleIngestError("run_transfer_busy_or_unreconciled") from error
    try:
        attempt = run_home / attempt_id
        if attempt.exists() or attempt.is_symlink():
            raise BundleIngestError("attempt_already_reserved")
        # Only a trusted host callback may recognize a fully verified and
        # confirmed prior delivery; no agent request can set this callback.
        _require_reconciled_prior_attempts(run_home, prior_attempt_authorizer)
        try:
            attempt.mkdir(mode=0o700)
        except FileExistsError as error:
            raise BundleIngestError("attempt_already_reserved") from error
        result = {**binding, "attempt_id": attempt_id, "status": "unknown",
                  "bundle_sha256": None, "bundle_bytes": None}
        _durable_json(attempt / "result.json", result)
        try:
            payload = _bundle_bytes(run_dir / "workspace" / HANDOFF_NAME)
            frozen = attempt / "input.bundle"
            with frozen.open("xb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            result.update(status="frozen",
                          bundle_sha256=hashlib.sha256(payload).hexdigest(),
                          bundle_bytes=len(payload))
        except BundleIngestError as error:
            result.update(status="refused", reason=str(error))
        _durable_json(attempt / "result.json", result)
        return result
    finally:
        lock.unlink()
