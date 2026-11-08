"""Read admitted repositories with the source-owned spool, time and cache policy."""

from pathlib import Path, PurePosixPath
import hashlib
import os
import signal
from stat import S_ISREG
import subprocess
import tempfile
import time
from laomedo.skills.registry.settings import MAX_FILE_BYTES
from laomedo.skills.registry.errors import SkillStoreError
from laomedo.skills.registry.paths import validate_relative_path
from laomedo.skills.sources.errors import SourceError
from laomedo.skills.sources.models import (
    SkillRepositoryRef,
    SkillRepositoryState,
    SkillRepositoryEntry,
)
from laomedo.skills.sources.settings import MAX_ENTRIES
from laomedo.skills.sources.utils import excluded_parts


class GitSkillSource:
    """Own admitted repository reads, source cache accounting and isolated Git execution."""

    def __init__(self, state: Path, *, repository_provider=None):
        """Bind one source cache and optional trusted file-source test capability."""
        self.state = state
        self.repository_provider = repository_provider

    def _run(self, cwd, args, limit=4 * 1024 * 1024, *, deadline=float("inf")):
        """Run an isolated source read with its existing spool, time and cache checks."""
        env = {
            k: v
            for k, v in os.environ.items()
            if k.upper()
            in {
                "PATH",
                "SYSTEMROOT",
                "WINDIR",
                "SYSTEMDRIVE",
                "COMSPEC",
                "PATHEXT",
                "TEMP",
                "TMP",
            }
        }
        env.update(
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_TERMINAL_PROMPT="0",
            GIT_ASKPASS="",
            SSH_ASKPASS="",
        )
        command = [
            "git",
            "-c",
            "credential.helper=",
            "-c",
            "core.hooksPath=" + str(self.state / "no-hooks"),
            "-c",
            "http.followRedirects=false",
            "-c",
            "protocol.allow=never",
            "-c",
            "protocol.https.allow=always",
            *args,
        ]
        # A trusted fixture adapter may use file transport; it is not exposed by the service.
        if self.repository_provider:
            command[1:1] = ["-c", "protocol.file.allow=always"]
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=output,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=os.name != "nt",
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                ),
            )
            deadline = min(time.monotonic() + 45, deadline)
            try:
                while process.poll() is None:
                    if output.tell() > limit or time.monotonic() > deadline:
                        raise SourceError("repository_limit_exceeded")
                    if self._cache_bytes() > 128 * 1024 * 1024:
                        raise SourceError("repository_limit_exceeded")
                    time.sleep(0.05)
                output.seek(0)
                data = output.read(limit + 1)
                if process.returncode or len(data) > limit:
                    raise SourceError("repository_access_unavailable")
                return data
            finally:
                if process.poll() is None:
                    if os.name == "nt":
                        subprocess.run(
                            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                    else:
                        os.killpg(process.pid, signal.SIGKILL)
                    if process.poll() is None:
                        process.kill()
                process.wait()

    def _cache_bytes(self):
        """Count observed regular-file bytes while Git may remove temporary locks.

        A vanished entry contributes no bytes. Other inspection failures propagate
        so an unreadable cache cannot silently bypass the existing size bound.
        """
        total = 0
        for path in self.state.rglob("*"):
            try:
                observed = path.stat()
            except FileNotFoundError:
                continue
            if S_ISREG(observed.st_mode):
                total += observed.st_size
        return total

    def repository(self, source, refresh=False, *, deadline):
        """Clone or refresh the owned bare cache and capture bounded refs within the supplied deadline."""
        folder = self.state / hashlib.sha256(source.encode()).hexdigest()
        transport = (
            str(self.repository_provider(source))
            if self.repository_provider
            else source
        )
        if not folder.exists():
            with tempfile.TemporaryDirectory(
                dir=self.state, prefix="clone-"
            ) as temporary:
                pending = Path(temporary) / "repository"
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
        """Decode and admit bounded Git tree metadata before reading any blob content."""
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
                result[path] = SkillRepositoryEntry(mode=mode, kind=kind, object_id=oid)
            if len(result) > MAX_ENTRIES:
                raise SourceError("source_limit_exceeded")
        return result

    def read_blob(self, repo, entry, deadline):
        """Check a tree entry mode and byte size before returning its exact Git blob bytes."""
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
