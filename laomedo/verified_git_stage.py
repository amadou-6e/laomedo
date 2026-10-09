"""Import an immutable verified bundle into a disposable credential-free Git DB.

The caller may later classify and push from the same ``bare`` object store.
Nothing here reads an agent checkout, provider credential, or remote.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

from .bundle_stage import _single_bundle_commit, BundleStageError
from .github_git_transport import (_base_git_environment, _run_bounded_tree,
                                   GIT_COMMAND_TIMEOUT_SECONDS)
from .verified_stage import VerifiedStage
from .verified_stage import resolve_verified_stage
from .bundle_ingest import (_bound_roots, _record, freeze_run_bundle,
                            BundleIngestError)


_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class VerifiedGitStageError(RuntimeError):
    """Local Git staging or classification failed before provider contact."""


def make_grant_stage_resolver(runner_state: Path, private_root: Path,
                              agent_mount: Path):
    """Create a host-only resolver; the request never selects filesystem roots."""
    runner_state, private_root = _bound_roots(Path(runner_state),
                                               Path(private_root))
    mounted = Path(agent_mount).resolve()
    if (private_root == mounted or private_root.is_relative_to(mounted) or
            mounted.is_relative_to(private_root)):
        raise ValueError("stage_root_overlaps_agent_mount")

    def resolve(grant, repository: str, payload: dict) -> VerifiedStage:
        return resolve_verified_stage(
            runner_state, private_root, run_id=grant["run_id"],
            repository=repository, branch=grant["branch"],
            commit=payload.get("commit"),
            stage_attempt_id=payload.get("stage_attempt_id"),
            expected_grant_id=grant["grant_id"])
    return resolve


def make_grant_bundle_freezer(runner_state: Path, private_root: Path,
                              agent_mount: Path):
    """Bind an agent's fixed handoff file to its still-running run grant.

    This copies bytes only; Docker verification and provider effects remain
    separate. No request field selects a host path or a run identity.
    """
    runner_state, private_root = _bound_roots(Path(runner_state),
                                               Path(private_root))
    mounted = Path(agent_mount).resolve()
    if (private_root == mounted or private_root.is_relative_to(mounted) or
            mounted.is_relative_to(private_root)):
        raise ValueError("stage_root_overlaps_agent_mount")

    def freeze(grant, payload: dict) -> dict:
        if set(payload) != {"attempt_id"}:
            raise BundleIngestError("freeze_request_invalid")
        _, before = _record(runner_state, grant["run_id"])
        if (before.get("binding_mode") != "active" or
                before.get("grant_id") != grant["grant_id"] or
                before["repository"] != grant["repository"] or
                before["branch"] != grant["branch"]):
            raise BundleIngestError("run_grant_mismatch")
        result = freeze_run_bundle(runner_state, private_root,
                                   run_id=grant["run_id"],
                                   attempt_id=payload["attempt_id"])
        _, after = _record(runner_state, grant["run_id"])
        if (after != before or
                any(result.get(key) != value for key, value in before.items())):
            raise BundleIngestError("run_changed_during_freeze")
        return result
    return freeze


def classify_verified_workflow(snapshot: VerifiedStage) -> bool:
    with stage_verified_git(snapshot) as staged:
        return staged.classify_workflow_change()


class VerifiedGitStage:
    """One isolated object store created only from the S12 snapshot bytes."""

    def __init__(self, bare: Path, snapshot: VerifiedStage,
                 *, run=_run_bounded_tree):
        self.bare = bare
        self.snapshot = snapshot
        self.run = run

    def git(self, *args: str) -> subprocess.CompletedProcess:
        # Git 2.31 on Windows may ignore GIT_CONFIG_GLOBAL, so isolate both
        # home-based config locations as well as every Git command variable.
        with tempfile.TemporaryDirectory(prefix="laomedo-git-home-") as home:
            env = _base_git_environment()
            env.update({"HOME": home, "USERPROFILE": home,
                        "XDG_CONFIG_HOME": home})
            env.pop("HOMEDRIVE", None)
            env.pop("HOMEPATH", None)
            return self.run(["git", "-C", str(self.bare), *args],
                            capture_output=True, check=False,
                            timeout=GIT_COMMAND_TIMEOUT_SECONDS, env=env)

    def classify_workflow_change(self) -> bool:
        """Classify the exact object store that a later push must use."""
        baseline, commit = self.snapshot.baseline, self.snapshot.commit
        try:
            if (self.git("cat-file", "-t", baseline).stdout.strip() != b"commit" or
                    self.git("cat-file", "-t", commit).stdout.strip() != b"commit" or
                    self.git("merge-base", "--is-ancestor", baseline,
                             commit).returncode != 0):
                raise VerifiedGitStageError("stage_history_invalid")
            changed = self.git("diff", "--no-ext-diff", "--no-textconv",
                               "--name-only", "-z", "--no-renames", baseline,
                               commit)
            if changed.returncode:
                raise VerifiedGitStageError("stage_diff_invalid")
        except (OSError, subprocess.TimeoutExpired) as error:
            raise VerifiedGitStageError("stage_git_unavailable") from error
        return any(path.startswith(b".github/workflows/") for path in
                   changed.stdout.split(b"\0") if path)


@contextmanager
def stage_verified_git(snapshot: VerifiedStage, *, run=_run_bounded_tree):
    """Yield a fresh bare Git repo containing only the snapshot's objects.

    The raw bundle is written into the same private temporary directory and
    deleted with it. A later push must use ``stage.bare`` while this context
    remains open; it must not stage again from an agent checkout.
    """
    if (not isinstance(snapshot, VerifiedStage) or
            not _COMMIT.fullmatch(snapshot.commit) or
            not _COMMIT.fullmatch(snapshot.baseline) or
            hashlib.sha256(snapshot.bundle).hexdigest() != snapshot.bundle_sha256):
        raise VerifiedGitStageError("stage_snapshot_invalid")
    try:
        advertised = _single_bundle_commit(snapshot.bundle,
                                           "refs/heads/validated")
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
        stage = VerifiedGitStage(bare, snapshot, run=run)
        try:
            if (stage.git("init", "--bare", "--quiet").returncode or
                    stage.git("fetch", "--no-tags", "--no-write-fetch-head",
                              str(bundle),
                              "refs/heads/validated:refs/stage/validated").returncode or
                    stage.git("rev-parse", "refs/stage/validated").stdout.strip() !=
                    snapshot.commit.encode("ascii") or
                    stage.git("fsck", "--full", "--strict", "--no-reflogs").returncode):
                raise VerifiedGitStageError("stage_import_invalid")
        except (OSError, subprocess.TimeoutExpired) as error:
            raise VerifiedGitStageError("stage_git_unavailable") from error
        yield stage
