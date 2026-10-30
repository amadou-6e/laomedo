"""Agent working-state admission and preparation, composed with generic Git."""

from pathlib import Path
import shutil
from laomedo.git.command import GitCommandRunner
from laomedo.git.errors import GitCommandTimeout, GitOperationError
from laomedo.git.models import GitEnvironmentProfile, GitExecutionContext
from laomedo.git.repository import GitRepository
from laomedo.git.worktree import GitWorkingTree
from laomedo.agents.errors import RunnerError
from .errors import GitWorkspaceError
from .models import WorkspacePaths, WorkspaceSnapshot
from .settings import _SHA
from .utils import _copy_tree


class AgentWorkspace:
    """Own preparation of one run's files; dispatch and publication stay outside."""

    def __init__(
        self, paths: WorkspacePaths, *, runner: GitCommandRunner | None = None
    ):
        """Retain the canonical path pair; perform admission only when preparing."""
        self.paths = paths
        self.runner = runner if runner is not None else GitCommandRunner()

    def prepare(self, canonical: Path, *, git: bool) -> WorkspaceSnapshot:
        """Prepare the working directory and its canonical snapshot in existing order."""
        if git:
            baseline = self.prepare_git()
            source_hash = _copy_tree(
                self.paths.directory, canonical, exclude_root_git=True
            )
        else:
            baseline = None
            source_hash = _copy_tree(self.paths.source, self.paths.directory)
            if _copy_tree(self.paths.source, canonical) != source_hash:
                raise RunnerError("source_changed_during_snapshot")
        return WorkspaceSnapshot(source_hash=source_hash, baseline=baseline)

    def prepare_git(self) -> str:
        """Clone only an admitted clean root; retain cleanup uncertainty on failure."""
        try:
            return self._prepare_git()
        except GitCommandTimeout as error:
            raise GitWorkspaceError(error.code) from error

    def _prepare_git(self) -> str:
        """Keep Agent-specific admission separate from generic repository mechanics."""
        source, destination = self.paths.source, self.paths.directory
        if source.is_symlink() or destination.exists() or destination.is_symlink():
            raise GitWorkspaceError("git_workspace_path_invalid")
        source = source.expanduser().resolve()
        git_dir = source / ".git"
        if not source.is_dir() or not git_dir.is_dir() or git_dir.is_symlink():
            raise GitWorkspaceError("git_repository_root_required")
        with self.runner.isolated_home(GitEnvironmentProfile.WORKSPACE) as home:
            context = GitExecutionContext(
                profile=GitEnvironmentProfile.WORKSPACE, home=home
            )

            source_repository = GitRepository(
                source,
                context=context.model_copy(update={"hardened": True}),
                runner=self.runner,
            )
            source_tree = GitWorkingTree(source_repository)
            baseline = source_repository.resolve("HEAD", verify=True)
            if baseline is None or not _SHA.fullmatch(baseline):
                raise GitWorkspaceError("source_commit_invalid")
            indexed = source_tree.index_entries()
            if indexed is None:
                raise GitWorkspaceError("source_index_invalid")
            modes = {row.split(b" ", 1)[0] for row in indexed if row}
            if b"160000" in modes:
                raise GitWorkspaceError("submodule_source_unsupported")
            if b"120000" in modes:
                raise GitWorkspaceError("symlink_source_unsupported")
            if any(
                (path := row.split(b"\t", 1)[-1].replace(b"\\", b"/").lower())
                == b".agents/skills"
                or path.startswith(b".agents/skills/")
                for row in indexed
                if row
            ):
                raise GitWorkspaceError("tracked_skill_path_unsupported")
            if source_tree.sparse_enabled():
                raise GitWorkspaceError("sparse_source_unsupported")
            status = source_tree.status_porcelain()
            if status is None or status:
                raise GitWorkspaceError("source_not_clean")
            try:
                destination.mkdir()
            except FileExistsError as error:
                raise GitWorkspaceError("git_workspace_path_invalid") from error
            try:
                try:
                    tree = GitWorkingTree.clone_from(
                        source, destination, context=context, runner=self.runner
                    )
                except GitOperationError as error:
                    raise GitWorkspaceError(error.code) from error
                sha = baseline.decode("ascii")
                if not tree.checkout_detached(sha):
                    raise GitWorkspaceError("git_checkout_failed")
                if not tree.remove_remote("origin"):
                    raise GitWorkspaceError("git_remote_removal_failed")
                tracked_skills = tree.repository.run(
                    ["ls-files", "-z", "--", ".agents/skills"]
                )
                if tracked_skills.returncode or tracked_skills.stdout:
                    raise GitWorkspaceError("tracked_skill_path_unsupported")
                with (destination / ".git" / "info" / "exclude").open(
                    "a", encoding="utf-8", newline="\n"
                ) as exclusions:
                    exclusions.write("\n/.agents/skills/\n")
                final = tree.repository.resolve("HEAD", verify=True)
                remotes = tree.remotes()
                if final != baseline or remotes is None or remotes:
                    raise GitWorkspaceError("git_clone_verification_failed")
                return sha
            except BaseException:
                try:
                    if destination.exists():
                        shutil.rmtree(destination)
                except OSError as cleanup_error:
                    raise GitWorkspaceError(
                        "git_workspace_cleanup_unverified"
                    ) from cleanup_error
                raise
