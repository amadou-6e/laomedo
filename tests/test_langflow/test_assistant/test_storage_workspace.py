"""Selected project files enter the native workspace and preserve external edits."""

from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from pydantic import ValidationError

from laomedo.agents.workspaces.models import WorkspaceFiles
from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.storage.files import ProjectStorage
from laomedo.integrations.langflow.assistant.storage.models import (
    RepositoryLocation,
    RepositoryRegistration,
)
from laomedo.integrations.langflow.assistant.storage.workspace import (
    ProjectChatWorkspace,
)


class ProjectWorkspaceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.checkout = self.root / "checkout"
        (self.checkout / ".git").mkdir(parents=True)
        self.storage = ProjectStorage(self.root / "state")
        self.owner, self.conversation = uuid4(), uuid4()
        self.storage.register(
            self.owner, RepositoryRegistration(name="Project", path=str(self.checkout))
        )
        repository = self.storage.document(self.owner).repositories[0].id
        self.storage.configure_agent_files(
            self.owner, RepositoryLocation(repository_id=repository, path="agent-files")
        )
        self.notes = self.checkout / "agent-files" / "notes.md"
        self.notes.write_text("Initial notes", encoding="utf-8")
        self.workspace = ProjectChatWorkspace(self.storage)

    def test_shell_changes_and_new_files_persist_and_survive_binding_reload(self):
        files = self.workspace.prepare(self.owner, self.conversation)
        run = self.root / "run"
        run.mkdir()
        files.materialize(run)
        (run / "project" / "agent-files" / "notes.md").write_text(
            "Updated notes", encoding="utf-8"
        )
        (run / "project" / "agent-files" / "plan.md").write_text(
            "New plan", encoding="utf-8"
        )
        observed = WorkspaceFiles.from_workspace(run)
        ProjectChatWorkspace(ProjectStorage(self.root / "state")).persist(
            self.owner, self.conversation, observed
        )
        self.assertEqual(self.notes.read_text(), "Updated notes")
        self.assertEqual((self.notes.parent / "plan.md").read_text(), "New plan")
        self.workspace.persist(self.owner, self.conversation, observed)
        self.assertEqual(self.notes.read_text(), "Updated notes")

    def test_external_edit_is_not_overwritten_and_preflight_preserves_other_files(self):
        self.workspace.prepare(self.owner, self.conversation)
        self.notes.write_text("External edit", encoding="utf-8")
        with self.assertRaises(AssistantError) as caught:
            self.workspace.persist(
                self.owner,
                self.conversation,
                WorkspaceFiles(
                    files={
                        "project/agent-files/notes.md": "Shell edit",
                        "project/agent-files/new.md": "New",
                    }
                ),
            )
        self.assertEqual(caught.exception.code, "assistant_storage_file_changed")
        self.assertEqual(self.notes.read_text(), "External edit")
        self.assertFalse((self.notes.parent / "new.md").exists())

    def test_frozen_source_retry_and_locations_do_not_follow_settings_changes(self):
        initial = self.workspace.prepare(self.owner, self.conversation)
        self.notes.write_text("Later", encoding="utf-8")
        self.assertEqual(self.workspace.prepare(self.owner, self.conversation), initial)
        repository = self.storage.document(self.owner).repositories[0].id
        self.storage.configure_agent_files(
            self.owner,
            RepositoryLocation(repository_id=repository, path="another-folder"),
        )
        with self.assertRaises(AssistantError):
            self.workspace.persist(
                self.owner,
                self.conversation,
                WorkspaceFiles(files={"project/agent-files/notes.md": "Shell edit"}),
            )
        self.assertFalse((self.checkout / "another-folder" / "notes.md").exists())

    def test_shell_deletion_is_persisted_but_secrets_and_unknown_graphs_are_refused(
        self,
    ):
        self.workspace.prepare(self.owner, self.conversation)
        for relative in ("project/agent-files/.env", "project/graphs/unknown.json"):
            with self.subTest(relative=relative), self.assertRaises(AssistantError):
                self.workspace.persist(
                    self.owner,
                    self.conversation,
                    WorkspaceFiles(files={relative: "Secret"}),
                )
            self.assertTrue(self.notes.exists())
        self.workspace.persist(self.owner, self.conversation, WorkspaceFiles())
        self.assertFalse(self.notes.exists())

    def test_bundle_refuses_escape_reserved_metadata_and_body_overflow(self):
        for relative in (
            "project/../outside",
            "project/.GIT/config",
            "project/a\\b",
            "/project/file",
        ):
            with self.subTest(relative=relative), self.assertRaises(ValidationError):
                WorkspaceFiles(files={relative: "text"})
        with self.assertRaises(ValidationError):
            WorkspaceFiles(files={"project/agent-files/large": "x" * 262144})
