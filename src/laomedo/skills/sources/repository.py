"""Read admitted source repositories through the shared bounded Git boundary."""

from pathlib import Path, PurePosixPath
import hashlib
from laomedo.git.command import GitCommandRunner
from laomedo.git.errors import GitCommandLimitExceeded, GitCommandCleanupError
from laomedo.git.models import (
    GitCommand,
    GitExecutionContext,
    GitExecutionBudget,
    GitEnvironmentProfile,
    GitTreeEntry,
)
from laomedo.skills.inspection.settings import MAX_FILE_BYTES
from laomedo.skills.registry.errors import SkillStoreError
from laomedo.skills.registry.paths import validate_relative_path
from laomedo.skills.sources.errors import SourceError
from laomedo.skills.sources.models import SkillRepositoryRef, SkillRepositoryState
from laomedo.skills.sources.settings import MAX_ENTRIES
from laomedo.skills.sources.staging import SkillSourceStagingDirectory
from laomedo.skills.sources.utils import excluded_parts


class GitSkillSource:
    """Own source cache semantics; generic process policy stays in GitCommandRunner."""

    def __init__(self, state: Path, *, repository_provider=None, runner=None):
        self.state = state
        self.repository_provider = repository_provider
        self.runner = runner if runner is not None else GitCommandRunner()

    def _check_cache_budget(self):
        if (
            sum(path.stat().st_size for path in self.state.rglob("*") if path.is_file())
            > 128 * 1024 * 1024
        ):
            raise SourceError("repository_limit_exceeded")

    def _run(self, cwd, args, limit=4 * 1024 * 1024, *, deadline=float("inf")):
        profile = (
            GitEnvironmentProfile.ISOLATED_FILE_READ_ONLY
            if self.repository_provider
            else GitEnvironmentProfile.ISOLATED_HTTPS_READ_ONLY
        )
        command = GitCommand(
            arguments=args,
            cwd=cwd,
            context=GitExecutionContext(
                profile=profile, timeout=45.0, hooks_path=Path(self.state, "no-hooks")
            ),
            budget=GitExecutionBudget(
                stdout_limit=limit,
                operation_deadline=deadline,
                check_budget=self._check_cache_budget,
            ),
        )
        try:
            result = self.runner.run(command)
        except GitCommandLimitExceeded:
            raise SourceError("repository_limit_exceeded") from None
        except GitCommandCleanupError:
            raise SourceError("repository_cleanup_unverified") from None
        if result.returncode or len(result.stdout) > limit:
            raise SourceError("repository_access_unavailable")
        return result.stdout

    def repository(self, source, refresh=False, *, deadline):
        folder = self.state / hashlib.sha256(source.encode()).hexdigest()
        transport = (
            str(self.repository_provider(source))
            if self.repository_provider
            else source
        )
        if not folder.exists():
            staging = SkillSourceStagingDirectory(dir=self.state)
            with staging as temporary:
                pending = Path(temporary) / "repository"
                try:
                    self._run(
                        self.state,
                        [
                            "clone",
                            "--bare",
                            "--depth=1",
                            "--no-single-branch",
                            "--",
                            transport,
                            str(pending),
                        ],
                        deadline=deadline,
                    )
                except SourceError as error:
                    if error.code == "repository_cleanup_unverified":
                        staging.preserve()
                    raise
                pending.rename(folder)
        elif refresh:
            self._run(
                folder,
                [
                    "fetch",
                    "--prune",
                    "--depth=1",
                    "--tags",
                    "origin",
                    "+refs/heads/*:refs/heads/*",
                ],
                deadline=deadline,
            )
        refs = (
            self._run(
                folder,
                ["for-each-ref", "--format=%(refname)", "refs/heads", "refs/tags"],
                64 * 1024,
                deadline=deadline,
            )
            .decode()
            .splitlines()
        )
        if len(refs) > 32:
            raise SourceError("repository_limit_exceeded")
        result = []
        for ref in refs:
            commit = (
                self._run(
                    folder,
                    ["rev-parse", "--verify", ref + "^{commit}"],
                    1024,
                    deadline=deadline,
                )
                .decode()
                .strip()
            )
            result.append(
                SkillRepositoryRef(label=ref.removeprefix("refs/"), commit=commit)
            )
        if not result:
            raise SourceError("repository_revision_unavailable")
        return SkillRepositoryState(directory=folder, refs=result)

    def entries(self, repo, commit, deadline):
        raw = self._run(
            repo,
            ["ls-tree", "-rz", "--full-tree", commit],
            2 * 1024 * 1024,
            deadline=deadline,
        )
        result = {}
        for entry in raw.split(b"\x00"):
            if not entry:
                continue
            header, path = entry.split(b"\t", 1)
            mode, kind, oid = header.decode().split()
            path = path.decode("utf-8")
            try:
                validate_relative_path(path)
            except SkillStoreError:
                raise SourceError("source_bundle_unsafe") from None
            if any((ord(c) < 32 for c in path)):
                raise SourceError("source_bundle_unsafe")
            if not excluded_parts(PurePosixPath(path).parts[:-1]):
                if path in result:
                    raise SourceError("source_bundle_unsafe")
                result[path] = GitTreeEntry(mode=mode, kind=kind, object_id=oid)
            if len(result) > MAX_ENTRIES:
                raise SourceError("source_limit_exceeded")
        return result

    def read_blob(self, repo, entry, deadline):
        if entry.mode not in {"100644", "100755"} or entry.kind != "blob":
            raise SourceError("source_bundle_unsafe")
        if (
            int(
                self._run(
                    repo, ["cat-file", "-s", entry.object_id], 128, deadline=deadline
                )
            )
            > MAX_FILE_BYTES
        ):
            raise SourceError("source_limit_exceeded")
        return self._run(
            repo,
            ["cat-file", "blob", entry.object_id],
            MAX_FILE_BYTES,
            deadline=deadline,
        )
