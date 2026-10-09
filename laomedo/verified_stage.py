"""Resolve one verified Git bundle under a trusted run grant, without effects.

The agent supplies only an attempt identity. The host supplies the grant's run,
repository and branch; no path from an agent request is consulted here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import stat

from .bundle_ingest import (_bound_roots, _record, _redirected,
                            BundleIngestError, MAX_RECORD_BYTES, _IDENTITY)
from .bundle_stage import (_read_frozen, _single_bundle_commit,
                           BundleStageError, MAX_OUTPUT_BYTES, PINNED_IMAGE_ID)


class VerifiedStageError(RuntimeError):
    """Refusal before provider credentials or a Git transport are consulted."""


@dataclass(frozen=True)
class VerifiedStage:
    run_id: str
    attempt_id: str
    repository: str
    branch: str
    baseline: str
    commit: str
    bundle_sha256: str
    stage_digest: str
    bundle: bytes = field(repr=False)


def _read_regular(path: Path, limit: int) -> bytes:
    if _redirected(path) or not path.is_file():
        raise VerifiedStageError("stage_file_invalid")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as source:
            before = os.fstat(source.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or
                    before.st_size > limit):
                raise VerifiedStageError("stage_file_invalid")
            payload = source.read(limit + 1)
            after = os.fstat(source.fileno())
            current = path.lstat()
            identity = lambda value: (value.st_dev, value.st_ino, value.st_size,
                                      value.st_mtime_ns)
            if (len(payload) != before.st_size or len(payload) > limit or
                    identity(before) != identity(after) or
                    identity(before) != identity(current) or _redirected(path)):
                raise VerifiedStageError("stage_file_changed")
            return payload
    except OSError as error:
        raise VerifiedStageError("stage_file_unreadable") from error


def resolve_verified_stage(runner_state: Path, private_root: Path, *,
                           run_id: str, repository: str, branch: str,
                           commit: str, stage_attempt_id: str) -> VerifiedStage:
    """Return exact verified bytes, bound to the trusted grant scope.

    This is a credential-free local read. The caller must take ``run_id``,
    ``repository`` and ``branch`` from the validated grant, not from a request.
    """
    if not isinstance(stage_attempt_id, str) or not _IDENTITY.fullmatch(
            stage_attempt_id):
        raise VerifiedStageError("stage_identity_invalid")
    try:
        runner_state, private_root = _bound_roots(Path(runner_state),
                                                   Path(private_root))
        _, binding = _record(runner_state, run_id)
        attempt, frozen = _read_frozen(runner_state, private_root, run_id,
                                       stage_attempt_id)
    except (BundleIngestError, BundleStageError, OSError) as error:
        raise VerifiedStageError("stage_binding_invalid") from error
    if (binding["repository"] != repository or binding["branch"] != branch or
            frozen["advertised_commit"] != commit or
            frozen["baseline"] != binding["baseline"]):
        raise VerifiedStageError("stage_scope_mismatch")
    raw = _read_regular(attempt / "verification.json", MAX_RECORD_BYTES)
    try:
        verification = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise VerifiedStageError("stage_verification_invalid") from error
    container = verification.get("container") if isinstance(verification, dict) else None
    if (not isinstance(container, dict) or
            verification.get("status") != "verified" or
            verification.get("run_id") != run_id or
            verification.get("attempt_id") != stage_attempt_id or
            verification.get("source_bundle_sha256") != frozen["bundle_sha256"] or
            verification.get("baseline") != binding["baseline"] or
            verification.get("commit") != commit or
            verification.get("image_id") != PINNED_IMAGE_ID or
            not isinstance(verification.get("baseline_bundle_sha256"), str) or
            len(verification["baseline_bundle_sha256"]) != 64 or
            any(character not in "0123456789abcdef" for character in
                verification["baseline_bundle_sha256"]) or
            verification.get("policy_approved") is not False or
            container.get("status") != "verified" or
            container.get("cleanup_verified") is not True or
            container.get("success_marker_seen") is not True or
            container.get("limits_verified") is not True or
            container.get("export_class") != "ok"):
        raise VerifiedStageError("stage_verification_invalid")
    bundle = _read_regular(attempt / "verified.bundle", MAX_OUTPUT_BYTES)
    digest = hashlib.sha256(bundle).hexdigest()
    if (container.get("output_sha256") != digest or
            type(container.get("output_bytes")) is not int or
            container["output_bytes"] != len(bundle)):
        raise VerifiedStageError("stage_bundle_changed")
    try:
        advertised = _single_bundle_commit(bundle, "refs/heads/validated")
    except BundleStageError as error:
        raise VerifiedStageError("stage_bundle_invalid") from error
    if advertised != commit:
        raise VerifiedStageError("stage_commit_mismatch")
    identity = {"run_id": run_id, "attempt_id": stage_attempt_id,
                "run_record_sha256": binding["run_record_sha256"],
                "repository": repository, "branch": branch,
                "baseline": binding["baseline"], "commit": commit,
                "source_bundle_sha256": frozen["bundle_sha256"],
                "verified_bundle_sha256": digest}
    stage_digest = hashlib.sha256(json.dumps(identity, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    return VerifiedStage(run_id, stage_attempt_id, repository, branch,
                         binding["baseline"], commit, digest, stage_digest,
                         bundle)
