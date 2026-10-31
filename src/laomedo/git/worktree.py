"""Checked-out Git mechanics, separate from Agent admission and protected files."""

from pathlib import Path

from .command import GitCommandRunner
from .errors import GitOperationError
from .models import GitCommand, GitExecutionContext
from .repository import GitRepository


class GitWorkingTree:
    """Compose repository execution with checked-out working state operations."""

    def __init__(self, repository: GitRepository):
        """Retain the caller's repository/context; do not clone or modify files."""
        self.repository = repository

    @classmethod
    def clone_from(
        cls,
        source: Path,
        destination: Path,
        *,
        context: GitExecutionContext,
        runner: GitCommandRunner,
    ) -> "GitWorkingTree":
        """Clone independent objects without checkout, local shortcuts or hardlinks.

        The caller owns source admission, destination lifetime and error mapping.
        A failed clone never returns an admitted working-tree object.
        """
        result = runner.run(
            GitCommand(
                arguments=[
                    "clone",
                    "--no-local",
                    "--no-hardlinks",
                    "--no-checkout",
                    "--single-branch",
                    "--quiet",
                    str(source),
                    str(destination),
                ],
                context=context,
            )
        )
        if result.returncode:
            raise GitOperationError("git_clone_failed")
        return cls(GitRepository(destination, context=context, runner=runner))

    def checkout_detached(self, commit: str) -> bool:
        """Check out the caller-selected commit without attaching a branch."""
        return (
            self.repository.run(["checkout", "--quiet", "--detach", commit]).returncode
            == 0
        )

    def index_entries(self) -> list[bytes] | None:
        """Read stage/mode records without interpreting caller admission policy."""
        result = self.repository.run(["ls-files", "--stage", "-z"])
        return (
            [row for row in result.stdout.split(b"\0") if row]
            if result.returncode == 0
            else None
        )

    def status_porcelain(self) -> bytes | None:
        """Inspect tracked and untracked changes using the stable porcelain format."""
        result = self.repository.run(
            ["status", "--porcelain=v1", "--untracked-files=all"]
        )
        return result.stdout if result.returncode == 0 else None

    def sparse_enabled(self) -> bool:
        """Read the local sparse-checkout value using Git's admitted truth values."""
        result = self.repository.run(
            ["config", "--local", "--get", "core.sparseCheckout"]
        )
        return result.returncode == 0 and result.stdout.strip().lower() in {
            b"true",
            b"1",
            b"yes",
        }

    def remove_remote(self, name: str) -> bool:
        """Remove only the caller-selected remote configuration."""
        return self.repository.run(["remote", "remove", name]).returncode == 0

    def remotes(self) -> bytes | None:
        """Read remote names as bytes for the caller's exact verification."""
        result = self.repository.run(["remote"])
        return result.stdout.strip() if result.returncode == 0 else None
