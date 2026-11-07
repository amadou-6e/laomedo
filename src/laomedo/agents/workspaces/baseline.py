"""Create an independent Agent directory-mode Git baseline."""

from __future__ import annotations

from pathlib import Path
import stat

from laomedo.agents.workspaces.skills.errors import WorkspaceSkillError
from laomedo.git.command import GitCommandRunner
from laomedo.git.errors import GitCommandTimeout
from laomedo.git.models import GitEnvironmentProfile, GitExecutionContext
from laomedo.git.repository import GitRepository
from laomedo.skills.registry.files import is_link


def initialize(workspace: Path) -> None:
    """Create an independent baseline, never import host Git metadata or hooks."""
    if (workspace / ".git").exists():
        raise WorkspaceSkillError("workspace_git_metadata_conflict")
    runner = GitCommandRunner()
    with runner.isolated_home(
        GitEnvironmentProfile.WORKSPACE, prefix="laomedo-baseline-home-"
    ) as home:
        repository = GitRepository(
            workspace,
            runner=runner,
            context=GitExecutionContext(
                profile=GitEnvironmentProfile.WORKSPACE,
                home=home,
                extra_env={
                    "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000",
                    "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000",
                },
            ),
        )
        configuration = (
            ("core.autocrlf", "false"),
            ("core.hooksPath", str(home)),
            ("commit.gpgsign", "false"),
            ("user.name", "Laomedo Workspace"),
            ("user.email", "workspace@example.invalid"),
        )
        for arguments in (
            ["init", "--template="],
            ["add", "--force", "--all", "."],
            ["commit", "--allow-empty", "-m", "Pinned source baseline"],
        ):
            try:
                result = repository.run(arguments, configuration=configuration)
            except (OSError, GitCommandTimeout):
                raise WorkspaceSkillError(
                    "workspace_git_initialization_failed"
                ) from None
            if result.returncode:
                raise WorkspaceSkillError("workspace_git_initialization_failed")
        # Git marks newly created loose objects read-only on Windows. These are
        # private baseline files, so allow ordinary disposable-fixture cleanup.
        for item in (workspace / ".git" / "objects").rglob("*"):
            if item.is_file() and not is_link(item):
                item.chmod(item.stat().st_mode | stat.S_IWRITE)
