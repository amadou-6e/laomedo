"""Import an immutable verified bundle into a disposable credential-free Git DB.

The caller may later classify and push from the same ``bare`` object store.
Nothing here reads an agent checkout, provider credential, or remote."""

from __future__ import annotations

from pathlib import Path
import laomedo.github.transport.git.constants as _git_constants
import laomedo.github.transport.git.utils as _git_utils
import laomedo.host.publication.verified.errors as _verified_errors
import laomedo.host.publication.verified.models as _verified_models
import subprocess
import tempfile


class VerifiedGitStage:
    """One isolated object store created only from the S12 snapshot bytes."""

    def __init__(
        self,
        bare: Path,
        snapshot: _verified_models.VerifiedStage,
        *,
        run=_git_utils._run_bounded_tree,
    ):
        self.bare = bare
        self.snapshot = snapshot
        self.run = run

    def git(self, *args: str) -> subprocess.CompletedProcess:
        # Git 2.31 on Windows may ignore GIT_CONFIG_GLOBAL, so isolate both
        # home-based config locations as well as every Git command variable.
        with tempfile.TemporaryDirectory(prefix="laomedo-git-home-") as home:
            env = _git_utils._base_git_environment()
            env.update({"HOME": home, "USERPROFILE": home, "XDG_CONFIG_HOME": home})
            env.pop("HOMEDRIVE", None)
            env.pop("HOMEPATH", None)
            return self.run(
                ["git", "-C", str(self.bare), *args],
                capture_output=True,
                check=False,
                timeout=_git_constants.GIT_COMMAND_TIMEOUT_SECONDS,
                env=env,
            )

    def classify_workflow_change(self) -> bool:
        """Classify the exact object store that a later push must use."""
        baseline, commit = self.snapshot.baseline, self.snapshot.commit
        try:
            if (
                self.git("cat-file", "-t", baseline).stdout.strip() != b"commit"
                or self.git("cat-file", "-t", commit).stdout.strip() != b"commit"
                or self.git("merge-base", "--is-ancestor", baseline, commit).returncode
                != 0
            ):
                raise _verified_errors.VerifiedGitStageError("stage_history_invalid")
            changed = self.git(
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--name-only",
                "-z",
                "--no-renames",
                baseline,
                commit,
            )
            if changed.returncode:
                raise _verified_errors.VerifiedGitStageError("stage_diff_invalid")
        except (OSError, subprocess.TimeoutExpired) as error:
            raise _verified_errors.VerifiedGitStageError(
                "stage_git_unavailable"
            ) from error
        return any(
            path.startswith(b".github/workflows/")
            for path in changed.stdout.split(b"\0")
            if path
        )
