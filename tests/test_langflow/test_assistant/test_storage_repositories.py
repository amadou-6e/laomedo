"""Real Git checkout, failed clone cleanup and private request boundaries."""

from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from pydantic import SecretStr, ValidationError

from laomedo.git.command import GitCommandRunner
from laomedo.git.models import GitCommand, GitExecutionContext
from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.storage.files import ProjectStorage
from laomedo.integrations.langflow.assistant.storage.models import RepositoryClone
from laomedo.integrations.langflow.assistant.storage.repositories import (
    ProjectRepositories,
)


class LocalRemoteRunner(GitCommandRunner):
    """Replace only the test remote with an owned repository; execute real Git."""

    def __init__(self, source):
        self.source = source
        self.commands = []

    def run(self, command):
        self.commands.append(command)
        arguments = list(command.arguments)
        if arguments[0] == "clone":
            arguments[-2] = str(self.source)
            command = command.model_copy(
                update={
                    "arguments": arguments,
                    "configuration": [
                        *command.configuration,
                        ("protocol.file.allow", "always"),
                    ],
                }
            )
        return super().run(command)


class ProjectRepositoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.runner = LocalRemoteRunner(self.source)
        self.git(["init", "--quiet"])
        (self.source / "notes.md").write_text("Project notes", encoding="utf-8")
        self.git(["add", "notes.md"])
        self.git(
            [
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "--quiet",
                "-m",
                "Initial",
            ]
        )
        self.storage = ProjectStorage(self.root / "storage")
        self.owner = uuid4()

    def git(self, arguments):
        result = GitCommandRunner().run(
            GitCommand(
                arguments=arguments,
                directory=self.source,
                context=GitExecutionContext(hardened=True),
            )
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_clone_registers_completed_checkout_without_storing_credentials(
        self,
    ):
        request = RepositoryClone(
            name="Project",
            repository="example/project",
            token=SecretStr("not-a-real-token"),
        )
        ProjectRepositories(self.storage, runner=self.runner).clone(self.owner, request)
        repository = self.storage.document(self.owner).repositories[0]
        self.assertEqual(
            (Path(repository.path) / "notes.md").read_text(), "Project notes"
        )
        config = (Path(repository.path) / ".git" / "config").read_text()
        self.assertIn('[remote "origin"]', config)
        self.assertNotIn("credential", config)
        self.assertNotIn("not-a-real-token", config)
        self.assertNotIn("not-a-real-token", request.model_dump_json())
        self.assertNotIn(
            "not-a-real-token", self.storage.document_path(self.owner).read_text()
        )
        self.assertTrue(
            all(command.context.hardened for command in self.runner.commands)
        )

    def test_submodule_mode_is_refused_before_checkout_and_registration(self):
        result = GitCommandRunner().run(
            GitCommand(
                arguments=["rev-parse", "HEAD"],
                directory=self.source,
                context=GitExecutionContext(),
            )
        )
        commit = result.stdout.decode().strip()
        self.git(
            ["update-index", "--add", "--cacheinfo", "160000," + commit + ",nested"]
        )
        self.git(
            [
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "--quiet",
                "-m",
                "Submodule",
            ]
        )
        with self.assertRaises(AssistantError) as caught:
            ProjectRepositories(self.storage, runner=self.runner).clone(
                self.owner,
                RepositoryClone(name="Project", repository="example/project"),
            )
        self.assertEqual(
            caught.exception.code, "assistant_storage_repository_unsupported"
        )
        self.assertEqual(self.storage.document(self.owner).repositories, [])
        self.assertEqual(
            list((self.storage.root / "checkouts" / str(self.owner)).iterdir()), []
        )

    def test_repository_selection_cannot_supply_url_credentials_or_native_options(self):
        for value in (
            "https://secret@github.com/a/b",
            "--upload-pack=evil",
            "../repo",
            "a/b/c",
            "a/b?token=secret",
        ):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                RepositoryClone(name="Project", repository=value)
