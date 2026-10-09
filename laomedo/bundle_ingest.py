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
        record_bytes = source.read_bytes()
        record = json.loads(record_bytes)
    except (OSError, ValueError) as error:
        raise BundleIngestError("run_binding_invalid") from error
    scope = record.get("github_scope") or {}
    branch = scope.get("branch")
    repository = scope.get("repository")
    baseline = record.get("git_baseline")
    if (record.get("run_id") != run_id or
            record.get("status") != "completed" or
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
    return run_dir, {"run_id": run_id,
                     "run_record_sha256": hashlib.sha256(record_bytes).hexdigest(),
                     "repository": repository,
                     "branch": branch, "baseline": baseline}


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


def freeze_run_bundle(runner_state: Path, private_root: Path, *, run_id: str,
                      attempt_id: str) -> dict:
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
