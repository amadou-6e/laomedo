"""Object-database mechanics shared by workspace, transport and publication callers."""

from pathlib import Path
import subprocess

from .command import GitCommandRunner
from .models import GitCommand, GitCredential, GitExecutionContext


class GitRepository:
    """Bind native Git mechanics to one repository and admitted execution context.

    The caller chooses allowed objects, remotes and effects. This object supplies
    shared command flags and isolation, never a grant or publication decision.
    """

    def __init__(
        self,
        path: Path,
        *,
        context: GitExecutionContext,
        runner: GitCommandRunner | None = None,
    ):
        """Retain the caller-owned resource without creating or admitting a repository."""
        self.path, self.context = Path(path), context
        self.runner = runner if runner is not None else GitCommandRunner()

    def run(
        self,
        arguments: list[str],
        *,
        credential: GitCredential | None = None,
        configuration: tuple[tuple[str, str], ...] = (),
    ) -> subprocess.CompletedProcess:
        """Execute one trusted native operation through the sole process runner."""
        return self.runner.run(
            GitCommand(
                arguments=arguments,
                directory=self.path,
                context=self.context,
                credential=credential,
                configuration=list(configuration),
            )
        )

    def init_bare(self, *, empty_template: bool = False) -> bool:
        """Initialize the caller's object store with its existing template policy."""
        args = ["init", "--bare", "--quiet"]
        if empty_template:
            args.append("--template=")
        return self.run(args).returncode == 0

    def fetch(
        self, source: str, refspec: str, *, credential: GitCredential | None = None
    ) -> bool:
        """Fetch exactly the supplied refspec without tags or FETCH_HEAD mutation."""
        return (
            self.run(
                ["fetch", "--no-tags", "--no-write-fetch-head", source, refspec],
                credential=credential,
            ).returncode
            == 0
        )

    def object_type(self, revision: str) -> bytes | None:
        """Read the native object type; missing/unreadable objects have no type."""
        result = self.run(["cat-file", "-t", revision])
        return result.stdout.strip() if result.returncode == 0 else None

    def is_ancestor(self, baseline: str, commit: str) -> bool:
        """Inspect ancestry without allowing an external diff program."""
        return (
            self.run(["merge-base", "--is-ancestor", baseline, commit]).returncode == 0
        )

    def changed_paths(self, baseline: str, commit: str) -> list[bytes] | None:
        """Read NUL-delimited changed paths with external diff/text conversion disabled."""
        result = self.run(
            [
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--name-only",
                "-z",
                "--no-renames",
                baseline,
                commit,
            ]
        )
        return (
            [path for path in result.stdout.split(b"\0") if path]
            if result.returncode == 0
            else None
        )

    def resolve(self, revision: str, *, verify: bool = False) -> bytes | None:
        """Read a revision identity as bytes, leaving admission/shape checks to its caller."""
        result = self.run(["rev-parse", *(["--verify"] if verify else []), revision])
        return result.stdout.strip() if result.returncode == 0 else None

    def check_ref_format(self, reference: str) -> bool:
        """Validate native ref syntax without selecting or authorizing that ref."""
        return self.run(["check-ref-format", reference]).returncode == 0

    def fsck(self, *, no_reflogs: bool = False) -> bool:
        """Inspect object connectivity under the caller's existing reflog policy."""
        return (
            self.run(
                [
                    "fsck",
                    "--full",
                    "--strict",
                    *(["--no-reflogs"] if no_reflogs else []),
                ]
            ).returncode
            == 0
        )
