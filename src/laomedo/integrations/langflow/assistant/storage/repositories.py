"""User-selected remote clones, isolated from host Git configuration and credentials."""

import os
import shutil
import subprocess
from uuid import UUID, uuid4

from laomedo.git.command import GitCommandRunner
from laomedo.git.models import GitCommand, GitCredential, GitExecutionContext
from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.storage.models import (
    RepositoryRegistration,
)


class ProjectRepositories:
    """Clone one selected repository; never execute its hooks, submodules or filters."""

    def __init__(self, storage, *, runner=None):
        self.storage = storage
        self.runner = runner or GitCommandRunner()

    def clone(self, owner, request):
        """Publish a registration only after clone and safe regular-file checkout."""
        directory = (
            self.storage.root / "checkouts" / str(UUID(str(owner))) / str(uuid4())
        )
        # Check every existing ancestor before creating any owned directories.
        if any(
            p.is_symlink() or p.is_junction() for p in (directory, *directory.parents)
        ):
            raise AssistantError("assistant_storage_path_invalid", 422)
        configuration = [
            ("credential.helper", ""),
            ("http.followRedirects", "false"),
            ("protocol.allow", "never"),
            ("protocol.https.allow", "always"),
            ("filter.lfs.required", "false"),
            ("filter.lfs.smudge", ""),
            ("filter.lfs.process", ""),
        ]
        credential = GitCredential(token=request.token) if request.token else None
        registered = False
        try:
            directory.parent.mkdir(parents=True, exist_ok=True)
            with self.runner.isolated_home(GitExecutionContext().profile) as home:
                context = GitExecutionContext(home=home, hardened=True, timeout=90)

                command = GitCommand(
                    arguments=[],
                    context=context,
                    configuration=configuration,
                    credential=credential,
                )
                self.run(
                    command,
                    [
                        "clone",
                        "--quiet",
                        "--depth=1",
                        "--no-checkout",
                        "--no-recurse-submodules",
                        "--",
                        "https://github.com/" + request.repository + ".git",
                        str(directory),
                    ],
                )
                self.checkout(command, directory)
                # Origin retains only the selected credential-free repository URL.
                # Native providers receive selected files, never this .git directory.
            result = self.storage.register(
                owner, RepositoryRegistration(name=request.name, path=str(directory))
            )
            registered = True
            return result
        except (OSError, subprocess.TimeoutExpired, ValueError):
            raise AssistantError("assistant_storage_clone_failed", 503) from None
        finally:
            credential = None
            if not registered and directory.exists():
                # Only this fresh UUID child, never a caller-provided checkout.
                if directory.parent.parent.parent != self.storage.root:
                    raise RuntimeError("invalid_owned_clone_directory")
                shutil.rmtree(directory, onerror=self._remove_readonly)

    def checkout(self, command, directory):
        """Permit an empty remote; inspect nonempty trees before materialization."""
        refs = self.run(
            command, ["for-each-ref", "--format=%(refname)"], directory=directory
        )
        if not refs.strip():
            return
        entries = self.run(
            command,
            ["ls-tree", "-rz", "--full-tree", "HEAD"],
            directory=directory,
        ).split(b"\0")
        if len(entries) > 10001 or any(
            entry and not entry.startswith((b"100644 blob ", b"100755 blob "))
            for entry in entries
        ):
            raise AssistantError("assistant_storage_repository_unsupported", 422)
        self.run(
            command,
            ["checkout", "--quiet", "--detach", "HEAD"],
            directory=directory,
        )

    def run(self, command, arguments, *, directory=None):
        """Execute one private command; surface a safe domain code instead of stderr."""
        result = self.runner.run(
            command.model_copy(update={"arguments": arguments, "directory": directory})
        )
        if result.returncode:
            raise AssistantError("assistant_storage_clone_failed", 409)
        return result.stdout

    @staticmethod
    def _remove_readonly(function, path, _error):
        """Git objects can be read-only on Windows; cleanup stays in the owned tree."""
        os.chmod(path, 0o700)
        function(path)
