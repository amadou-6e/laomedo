"""Import an immutable verified bundle into a disposable credential-free Git DB.

The caller may later classify and push from the same ``bare`` object store.
Nothing here reads an agent checkout, provider credential, or remote."""

from __future__ import annotations

from pathlib import Path
from laomedo.git.command import GitCommandRunner
from laomedo.git.models import GitExecutionContext
from laomedo.git.repository import GitRepository
from laomedo.github.workflows.utils import touches_workflows
from laomedo.host.publication.verified.errors import VerifiedGitStageError
from laomedo.host.publication.verified.models import VerifiedStage
import subprocess


class VerifiedGitStage:
    """One isolated object store created only from the S12 snapshot bytes."""

    def __init__(
        self,
        bare: Path,
        snapshot: VerifiedStage,
        *,
        runner: GitCommandRunner | None = None,
    ):
        self.bare = bare
        self.snapshot = snapshot
        self.repository = GitRepository(
            bare,
            context=GitExecutionContext(ignore_home_cleanup_errors=False),
            runner=runner,
        )

    def classify_workflow_change(self) -> bool:
        """Classify the exact object store that a later push must use."""
        baseline, commit = self.snapshot.baseline, self.snapshot.commit
        try:
            if (
                self.repository.object_type(baseline) != b"commit"
                or self.repository.object_type(commit) != b"commit"
                or not self.repository.is_ancestor(baseline, commit)
            ):
                raise VerifiedGitStageError("stage_history_invalid")
            paths = self.repository.changed_paths(baseline, commit)
            if paths is None:
                raise VerifiedGitStageError("stage_diff_invalid")
        except (OSError, subprocess.TimeoutExpired) as error:
            raise VerifiedGitStageError("stage_git_unavailable") from error
        return touches_workflows(paths)
