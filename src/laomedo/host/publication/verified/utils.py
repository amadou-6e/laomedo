"""Resolve and freeze immutable verified Git stages."""

from __future__ import annotations
from laomedo.host.publication.verified.models import VerifiedStageIdentity

from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
from laomedo.git.command import GitCommandRunner
from laomedo.host.publication.bundle.settings import MAX_OUTPUT_BYTES
from laomedo.host.publication.bundle.settings import PINNED_IMAGE_ID
from laomedo.host.publication.bundle.errors import BundleStageError
from laomedo.host.publication.bundle.stage import _read_frozen
from laomedo.host.publication.bundle.stage import _single_bundle_commit
from laomedo.host.publication.verified.settings import _COMMIT
from laomedo.host.publication.verified.errors import VerifiedGitStageError
from laomedo.host.publication.verified.errors import VerifiedStageError
from laomedo.host.publication.verified.models import VerifiedStage
from laomedo.host.publication.ingestion.settings import MAX_RECORD_BYTES
from laomedo.host.publication.ingestion.settings import RUN_IDENTITY
from laomedo.host.publication.ingestion.errors import BundleIngestError
from laomedo.host.publication.ingestion.utils import validate_ingestion_roots
from laomedo.host.publication.ingestion.utils import read_run_binding
from laomedo.host.publication.ingestion.utils import is_redirected_path
from laomedo.host.publication.ingestion.utils import freeze_run_bundle
import os
import stat
import subprocess
import tempfile


def make_grant_stage_resolver(
    runner_state: Path, private_root: Path, agent_mount: Path
):
    """Create a host-only resolver; the request never selects filesystem roots."""
    runner_state, private_root = validate_ingestion_roots(
        Path(runner_state), Path(private_root)
    )
    mounted = Path(agent_mount).resolve()
    if (
        private_root == mounted
        or private_root.is_relative_to(mounted)
        or mounted.is_relative_to(private_root)
    ):
        raise ValueError("stage_root_overlaps_agent_mount")

    def resolve(grant, repository: str, payload: dict) -> VerifiedStage:
        return resolve_verified_stage(
            runner_state,
            private_root,
            run_id=grant["run_id"],
            repository=repository,
            branch=grant["branch"],
            commit=payload.get("commit"),
            stage_attempt_id=payload.get("stage_attempt_id"),
            expected_grant_id=grant["grant_id"],
        )

    return resolve


def make_grant_bundle_freezer(
    runner_state: Path,
    private_root: Path,
    agent_mount: Path,
    *,
    confirmed_stage_authorizer=None,
):
    """Bind an agent's fixed handoff file to its still-running run grant.

    This copies bytes only; Docker verification and provider effects remain
    separate. No request field selects a host path or a run identity.
    """
    runner_state, private_root = validate_ingestion_roots(
        Path(runner_state), Path(private_root)
    )
    mounted = Path(agent_mount).resolve()
    if (
        private_root == mounted
        or private_root.is_relative_to(mounted)
        or mounted.is_relative_to(private_root)
    ):
        raise ValueError("stage_root_overlaps_agent_mount")

    def freeze(grant, payload: dict) -> dict:
        if set(payload) != {"attempt_id"}:
            raise BundleIngestError("freeze_request_invalid")
        _, before = read_run_binding(runner_state, grant["run_id"])
        if (
            before.get("binding_mode") != "active"
            or before.get("grant_id") != grant["grant_id"]
            or before["repository"] != grant["repository"]
            or before["branch"] != grant["branch"]
        ):
            raise BundleIngestError("run_grant_mismatch")

        def confirm_prior(attempt_id):
            # The normal resolver checks immutable bytes, verification and
            # cleanup, the current run binding and this exact grant first.
            _, prior = _read_frozen(
                runner_state, private_root, grant["run_id"], attempt_id
            )
            snapshot = resolve_verified_stage(
                runner_state,
                private_root,
                run_id=grant["run_id"],
                repository=grant["repository"],
                branch=grant["branch"],
                commit=prior["advertised_commit"],
                stage_attempt_id=attempt_id,
                expected_grant_id=grant["grant_id"],
            )
            return confirmed_stage_authorizer(grant, snapshot) is True

        result = freeze_run_bundle(
            runner_state,
            private_root,
            run_id=grant["run_id"],
            attempt_id=payload["attempt_id"],
            prior_attempt_authorizer=(
                confirm_prior if confirmed_stage_authorizer is not None else None
            ),
        )
        _, after = read_run_binding(runner_state, grant["run_id"])
        if after != before or any(
            result.get(key) != value for key, value in before.items()
        ):
            raise BundleIngestError("run_changed_during_freeze")
        return result

    return freeze


def classify_verified_workflow(snapshot: VerifiedStage) -> bool:
    with stage_verified_git(snapshot) as staged:
        return staged.classify_workflow_change()


@contextmanager
def stage_verified_git(
    snapshot: VerifiedStage, *, runner: GitCommandRunner | None = None
):
    """Yield a fresh bare Git repo containing only the snapshot's objects.

    The raw bundle is written into the same private temporary directory and
    deleted with it. A later push must use ``stage.bare`` while this context
    remains open; it must not stage again from an agent checkout.
    """
    from laomedo.host.publication.verified.git import VerifiedGitStage

    if (
        not isinstance(snapshot, VerifiedStage)
        or not _COMMIT.fullmatch(snapshot.commit)
        or not _COMMIT.fullmatch(snapshot.baseline)
        or hashlib.sha256(snapshot.bundle).hexdigest() != snapshot.bundle_sha256
    ):
        raise VerifiedGitStageError("stage_snapshot_invalid")
    try:
        advertised = _single_bundle_commit(snapshot.bundle, "refs/heads/validated")
    except BundleStageError as error:
        raise VerifiedGitStageError("stage_bundle_invalid") from error
    if advertised != snapshot.commit:
        raise VerifiedGitStageError("stage_commit_mismatch")
    with tempfile.TemporaryDirectory(prefix="laomedo-verified-git-") as root:
        directory = Path(root)
        bare = directory / "objects.git"
        bare.mkdir()
        bundle = directory / "verified.bundle"
        bundle.write_bytes(snapshot.bundle)
        stage = VerifiedGitStage(bare, snapshot, runner=runner)
        try:
            if (
                not stage.repository.init_bare()
                or not stage.repository.fetch(
                    str(bundle), "refs/heads/validated:refs/stage/validated"
                )
                or stage.repository.resolve("refs/stage/validated")
                != snapshot.commit.encode("ascii")
                or not stage.repository.fsck(no_reflogs=True)
            ):
                raise VerifiedGitStageError("stage_import_invalid")
        except (OSError, subprocess.TimeoutExpired) as error:
            raise VerifiedGitStageError("stage_git_unavailable") from error
        yield stage


def _read_regular(path: Path, limit: int) -> bytes:
    if is_redirected_path(path) or not path.is_file():
        raise VerifiedStageError("stage_file_invalid")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as source:
            before = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or before.st_size > limit
            ):
                raise VerifiedStageError("stage_file_invalid")
            payload = source.read(limit + 1)
            after = os.fstat(source.fileno())
            current = path.lstat()
            identity = lambda value: (
                value.st_dev,
                value.st_ino,
                value.st_size,
                value.st_mtime_ns,
            )
            if (
                len(payload) != before.st_size
                or len(payload) > limit
                or identity(before) != identity(after)
                or identity(before) != identity(current)
                or is_redirected_path(path)
            ):
                raise VerifiedStageError("stage_file_changed")
            return payload
    except OSError as error:
        raise VerifiedStageError("stage_file_unreadable") from error


def resolve_verified_stage(
    runner_state: Path,
    private_root: Path,
    *,
    run_id: str,
    repository: str,
    branch: str,
    commit: str,
    stage_attempt_id: str,
    expected_grant_id: str | None = None,
) -> VerifiedStage:
    """Return exact verified bytes, bound to the trusted grant scope.

    This is a credential-free local read. The caller must take ``run_id``,
    ``repository`` and ``branch`` from the validated grant, not from a request.
    """
    if not isinstance(stage_attempt_id, str) or not RUN_IDENTITY.fullmatch(
        stage_attempt_id
    ):
        raise VerifiedStageError("stage_identity_invalid")
    try:
        runner_state, private_root = validate_ingestion_roots(
            Path(runner_state), Path(private_root)
        )
        _, binding = read_run_binding(runner_state, run_id)
        attempt, frozen = _read_frozen(
            runner_state, private_root, run_id, stage_attempt_id
        )
    except (
        BundleIngestError,
        BundleStageError,
        OSError,
    ) as error:
        raise VerifiedStageError("stage_binding_invalid") from error
    if expected_grant_id is not None and binding.get("binding_mode") != "active":
        raise VerifiedStageError("stage_run_not_active")
    if (
        binding.get("binding_mode") == "active"
        and binding.get("grant_id") != expected_grant_id
    ):
        raise VerifiedStageError("stage_grant_mismatch")
    if (
        binding["repository"] != repository
        or binding["branch"] != branch
        or frozen["advertised_commit"] != commit
        or frozen["baseline"] != binding["baseline"]
    ):
        raise VerifiedStageError("stage_scope_mismatch")
    raw = _read_regular(attempt / "verification.json", MAX_RECORD_BYTES)
    try:
        verification = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise VerifiedStageError("stage_verification_invalid") from error
    container = (
        verification.get("container") if isinstance(verification, dict) else None
    )
    if (
        not isinstance(container, dict)
        or verification.get("status") != "verified"
        or verification.get("run_id") != run_id
        or verification.get("attempt_id") != stage_attempt_id
        or verification.get("source_bundle_sha256") != frozen["bundle_sha256"]
        or verification.get("baseline") != binding["baseline"]
        or verification.get("commit") != commit
        or verification.get("image_id") != PINNED_IMAGE_ID
        or not isinstance(verification.get("baseline_bundle_sha256"), str)
        or len(verification["baseline_bundle_sha256"]) != 64
        or any(
            character not in "0123456789abcdef"
            for character in verification["baseline_bundle_sha256"]
        )
        or verification.get("policy_approved") is not False
        or container.get("status") != "verified"
        or container.get("cleanup_verified") is not True
        or container.get("success_marker_seen") is not True
        or container.get("limits_verified") is not True
        or container.get("export_class") != "ok"
    ):
        raise VerifiedStageError("stage_verification_invalid")
    bundle = _read_regular(attempt / "verified.bundle", MAX_OUTPUT_BYTES)
    digest = hashlib.sha256(bundle).hexdigest()
    if (
        container.get("output_sha256") != digest
        or type(container.get("output_bytes")) is not int
        or container["output_bytes"] != len(bundle)
    ):
        raise VerifiedStageError("stage_bundle_changed")
    try:
        advertised = _single_bundle_commit(bundle, "refs/heads/validated")
    except BundleStageError as error:
        raise VerifiedStageError("stage_bundle_invalid") from error
    if advertised != commit:
        raise VerifiedStageError("stage_commit_mismatch")
    binding_identity = (
        {"run_binding_sha256": binding["run_binding_sha256"]}
        if binding.get("binding_mode") == "active"
        else {"run_record_sha256": binding["run_record_sha256"]}
    )
    identity = VerifiedStageIdentity(
        run_id=run_id,
        attempt_id=stage_attempt_id,
        **binding_identity,
        repository=repository,
        branch=branch,
        baseline=binding["baseline"],
        commit=commit,
        source_bundle_sha256=frozen["bundle_sha256"],
        verified_bundle_sha256=digest,
    )
    return VerifiedStage.from_identity(identity, bundle)
