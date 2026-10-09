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


def transfer(record: dict, runner_state: Path, private_root: Path,
             trusted_source: Path, *, attempt_id: str,
             confirmed: dict | None = None) -> dict:
    """Freeze exact bytes and stage only a verified, run-bound commit.

    ``confirmed`` is host-private prior-stage metadata, never agent input.
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
    if (private_root == run_dir or private_root.is_relative_to(run_dir) or
            run_dir.is_relative_to(private_root) or
            trusted_source.is_relative_to(run_dir)):
        raise HandoffError("private_stage_boundary_invalid")
    source = trusted_source
    confirmed_commit = None
    if confirmed is not None:
        if (confirmed.get("run_id") != run_id or confirmed.get("branch") != branch or
                not isinstance(confirmed.get("commit"), str) or
                not _SHA.fullmatch(confirmed["commit"]) or
                not isinstance(confirmed.get("stage"), str)):
            raise HandoffError("confirmed_stage_invalid")
        source = Path(confirmed["stage"]).resolve(strict=True)
        if not source.is_relative_to(private_root) or not source.is_dir():
            raise HandoffError("confirmed_stage_invalid")
        confirmed_commit = confirmed["commit"]
    attempt = private_root / f"{run_id}-{attempt_id}"
    attempt.mkdir(mode=0o700)  # a repeated/uncertain attempt is never overwritten
    result = {"run_id": run_id, "attempt_id": attempt_id, "branch": branch,
              "baseline": record["git_baseline"], "reason": "unknown",
              "commit": None, "tree": None, "stage": None}
    try:
        payload = _bytes_from_agent(run_dir / "workspace" / HANDOFF_NAME)
        frozen = attempt / "frozen.bundle"
        with frozen.open("xb") as stream:
            stream.write(payload)
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
        temporary = attempt / "result.pending"
        temporary.write_text(json.dumps(result, sort_keys=True) + "\n",
                             encoding="utf-8")
        os.replace(temporary, attempt / "result.json")
    return result
