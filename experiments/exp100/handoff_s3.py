"""Credential-free S3 prototype: bind one agent bundle to a saved run.

This is experiment code, not a provider-facing product endpoint. It never
reads a token, runs Git in the agent checkout, or sends a remote write.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat

from experiments.exp100.bundle_transfer import (MAX_BUNDLE_BYTES, git,
                                                verify_bundle)


_IDENTITY = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
HANDOFF_NAME = ".laomedo-handoff.bundle"


class HandoffError(RuntimeError):
    """Known refusal of one local transfer attempt."""


def _plain_file(path: Path) -> bool:
    try:
        mode = path.lstat()
    except OSError:
        return False
    return (stat.S_ISREG(mode.st_mode) and mode.st_nlink == 1 and
            not bool(getattr(mode, "st_file_attributes", 0) &
                     getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)))


def _bytes_from_agent(path: Path) -> bytes:
    if not _plain_file(path):
        raise HandoffError("handoff_not_regular")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or
                    opened.st_size > MAX_BUNDLE_BYTES):
                raise HandoffError("handoff_size_or_type")
            payload = stream.read(MAX_BUNDLE_BYTES + 1)
            if len(payload) > MAX_BUNDLE_BYTES or len(payload) != opened.st_size:
                raise HandoffError("handoff_changed_or_oversized")
            if not _plain_file(path) or os.stat(path, follow_symlinks=False).st_ino != opened.st_ino:
                raise HandoffError("handoff_replaced")
            return payload
    except OSError as error:
        raise HandoffError("handoff_unreadable") from error


def _stage_git(stage: Path, source: Path, baseline: str,
               confirmed_commit: str | None, frozen: Path, commit: str) -> None:
    if git(["init", "--bare", "--quiet", str(stage)]).returncode:
        raise HandoffError("stage_init_failed")
    for seed in (baseline, confirmed_commit):
        if seed is None:
            continue
        if git(["fetch", "--no-tags", str(source), seed], directory=stage).returncode:
            raise HandoffError("stage_seed_failed")
    if git(["bundle", "unbundle", str(frozen)], directory=stage).returncode:
        raise HandoffError("stage_import_failed")
    if git(["fsck", "--strict", "--no-reflogs", commit], directory=stage).returncode:
        raise HandoffError("stage_integrity_failed")
    if confirmed_commit and git(["merge-base", "--is-ancestor",
                                 confirmed_commit, commit], directory=stage).returncode:
        raise HandoffError("confirmed_ancestry_invalid")


def _durable_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".pending")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    if os.name != "nt":
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def _accepted_head(private_root: Path, run_id: str, branch: str) -> dict | None:
    accepted = {}
    for attempt in (private_root / run_id).glob("*"):
        path = attempt / "result.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise HandoffError("attempt_unreconciled") from error
        if value.get("run_id") != run_id or value.get("reason") == "unknown":
            raise HandoffError("attempt_unreconciled")
        if (value.get("run_id") == run_id and value.get("branch") == branch and
                value.get("reason") == "accepted"):
            accepted[value["attempt_id"]] = value
    if not accepted:
        return None
    predecessors = {value.get("previous_attempt_id") for value in accepted.values()}
    heads = [value for key, value in accepted.items() if key not in predecessors]
    if len(heads) != 1:
        raise HandoffError("confirmed_history_ambiguous")
    return heads[0]


def transfer(record: dict, runner_state: Path, private_root: Path,
             trusted_source: Path, *, attempt_id: str,
             confirmed_attempt_id: str | None = None) -> dict:
    """Freeze exact bytes and stage only a verified, run-bound commit.

    ``confirmed_attempt_id`` selects a host-private prior-stage record, never
    an agent path or a dict supplied by the agent.
    The caller owns the run record, runner state, private root and trusted
    source selection. No agent-supplied path selects the handoff file.
    """
    run_id = record.get("run_id")
    scope = record.get("github_scope") or {}
    branch = scope.get("branch")
    if (not isinstance(run_id, str) or not _IDENTITY.fullmatch(run_id) or
            not isinstance(attempt_id, str) or not _IDENTITY.fullmatch(attempt_id) or
            record.get("workspace_mode") != "git" or
            record.get("status") != "completed" or
            not isinstance(branch, str) or
            not re.fullmatch(r"[A-Za-z0-9._/-]+", branch) or
            not isinstance(record.get("git_baseline"), str) or
            not _SHA.fullmatch(record["git_baseline"])):
        raise HandoffError("run_binding_invalid")
    try:
        runner_state = runner_state.resolve(strict=True)
        run_dir = (runner_state / "runs" / run_id).resolve(strict=True)
    except OSError as error:
        raise HandoffError("run_binding_invalid") from error
    if run_dir.parent != runner_state / "runs":
        raise HandoffError("run_binding_invalid")
    private_root = private_root.resolve(strict=True)
    trusted_source = trusted_source.resolve(strict=True)
    if (private_root == runner_state or private_root.is_relative_to(runner_state) or
            runner_state.is_relative_to(private_root) or
            trusted_source.is_relative_to(run_dir)):
        raise HandoffError("private_stage_boundary_invalid")
    lock = private_root / f"{run_id}.lock"
    try:
        with lock.open("x", encoding="ascii") as stream:
            stream.write(attempt_id + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise HandoffError("run_transfer_busy_or_unreconciled") from error
    try:
        # A stale lock is a crash/unknown signal, not a lock to steal. An
        # operator must inspect the run journal before manual reconciliation.
        run_home = private_root / run_id
        run_home.mkdir(exist_ok=True, mode=0o700)
        attempt = run_home / attempt_id
        if attempt.exists():
            raise HandoffError("attempt_already_reserved")
        head = _accepted_head(private_root, run_id, branch)
        if (head is None and confirmed_attempt_id is not None) or \
                (head is not None and confirmed_attempt_id != head["attempt_id"]):
            raise HandoffError("confirmed_stage_required")
        source = trusted_source
        confirmed_commit = None
        if head is not None:
            confirmed_commit = head.get("commit")
            if not isinstance(confirmed_commit, str) or not _SHA.fullmatch(confirmed_commit):
                raise HandoffError("confirmed_stage_invalid")
            source = run_home / confirmed_attempt_id / "stage.git"
            if not source.is_dir() or source.is_symlink():
                raise HandoffError("confirmed_stage_invalid")
        try:
            attempt.mkdir(mode=0o700)  # repeat identity cannot overwrite evidence
        except FileExistsError as error:
            raise HandoffError("attempt_already_reserved") from error
        result = {"run_id": run_id, "attempt_id": attempt_id, "branch": branch,
                  "baseline": record["git_baseline"], "reason": "unknown",
                  "previous_attempt_id": confirmed_attempt_id,
                  "commit": None, "tree": None, "stage": None}
        _durable_json(attempt / "result.json", result)
        try:
            payload = _bytes_from_agent(run_dir / "workspace" / HANDOFF_NAME)
            frozen = attempt / "frozen.bundle"
            with frozen.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            result["bundle_sha256"] = hashlib.sha256(payload).hexdigest()
            checked = verify_bundle(payload, trusted_source=source,
                                    baseline=record["git_baseline"],
                                    expected_ref="refs/heads/" + branch,
                                    confirmed_commit=confirmed_commit)
            result.update(reason=checked["reason"], commit=checked["commit"],
                          tree=checked["tree"])
            if checked["reason"] == "accepted":
                stage = attempt / "stage.git"
                _stage_git(stage, source, record["git_baseline"],
                           confirmed_commit, frozen, checked["commit"])
                result["stage"] = str(stage)
        except HandoffError as error:
            result["reason"] = str(error)
        finally:
            _durable_json(attempt / "result.json", result)
        return result
    finally:
        lock.unlink()
