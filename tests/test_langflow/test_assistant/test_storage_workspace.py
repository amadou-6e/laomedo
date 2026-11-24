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
        self.assertEqual(caught.exception.code, "assistant_storage_workspace_conflict")
        self.assertEqual(self.notes.read_text(), "External edit")
        self.assertFalse((self.notes.parent / "new.md").exists())

        # Restore the current repository text in the native workspace, then resume.
        # Identical-content acceptance rebaselines safely without overwriting it.
        current = self.storage.read_file(
            self.owner,
            "notes.md",
            document=self.workspace.document(self.owner, self.conversation),
        )["content"]
        self.workspace.persist(
            self.owner,
            self.conversation,
            WorkspaceFiles(
                files={
                    "project/agent-files/notes.md": current,
                    "project/agent-files/new.md": "New",
                }
            ),
        )
        self.workspace.persist(
            self.owner,
            self.conversation,
            WorkspaceFiles(
                files={
                    "project/agent-files/notes.md": "Merged after recovery",
                    "project/agent-files/new.md": "New",
                }
            ),
        )
        self.assertEqual(self.notes.read_text(), "Merged after recovery")
        self.assertEqual((self.notes.parent / "new.md").read_text(), "New")

    def test_unsupported_file_can_be_removed_and_same_conversation_recovers(self):
        initial = self.workspace.prepare(self.owner, self.conversation)
        for relative in ("project/notes.md", "project/graphs/unknown.json"):
            with self.subTest(relative=relative):
                invalid = initial.model_copy(
                    update={"files": {**initial.files, relative: "Unsupported"}}
                )
                with self.assertRaisesRegex(
                    AssistantError, "assistant_storage_workspace_path_invalid"
                ):
                    self.workspace.persist(self.owner, self.conversation, invalid)
                self.workspace.persist(self.owner, self.conversation, initial)
        self.workspace.persist(
            self.owner,
            self.conversation,
            WorkspaceFiles(
                files={
                    "project/agent-files/notes.md": "Recovered",
                }
            ),
        )
        self.assertEqual(self.notes.read_text(), "Recovered")

    def test_chat_file_tools_keep_frozen_folder_and_graph_locations(self):
        repository = self.storage.document(self.owner).repositories[0].id
        graph = uuid4()
        old_graph = RepositoryLocation(
            repository_id=repository, path="graphs/original.json"
        )
        self.storage.replace(self.storage.graph_path(self.owner, old_graph), b"{}")
        self.storage.bind_graph(self.owner, graph, old_graph, "initial")
        self.workspace.prepare(self.owner, self.conversation)
        self.storage.configure_agent_files(
            self.owner, RepositoryLocation(repository_id=repository, path="new-folder")
        )
        self.storage.bind_graph(
            self.owner,
            graph,
            RepositoryLocation(repository_id=repository, path="graphs/new.json"),
            "other",
        )
        document = self.workspace.document(self.owner, self.conversation)
        self.assertEqual(
            self.storage.list_files(self.owner, document=document)["agent_files"],
            ["notes.md"],
        )
        self.assertEqual(
            self.storage.read_file(self.owner, "", str(graph), document=document)[
                "content"
            ],
            "{}",
        )
        from laomedo.integrations.langflow.assistant.storage.models import (
            AgentFileWrite,
        )

        observed = self.storage.read_file(self.owner, "notes.md", document=document)
        self.storage.write_file(
            self.owner,
            AgentFileWrite(
                path="notes.md",
                content="Tool write",
                expected_sha256=observed["sha256"],
            ),
            document=document,
        )
        self.assertEqual(self.notes.read_text(), "Tool write")
        self.assertFalse((self.checkout / "new-folder" / "notes.md").exists())

    def test_empty_selection_stays_empty_after_later_configuration(self):
        empty_conversation = uuid4()
        document = self.storage.document(self.owner)
        document.agent_files = None
        self.storage.save_document(self.owner, document)
        self.workspace.prepare(self.owner, empty_conversation)
        document.agent_files = RepositoryLocation(
            repository_id=document.repositories[0].id, path="agent-files"
        )
        self.storage.save_document(self.owner, document)
        frozen = self.workspace.document(self.owner, empty_conversation)
        self.assertIsNone(frozen.agent_files)

    def test_crlf_contents_survive_unmodified_roundtrip(self):
        self.notes.write_bytes(b"First\r\nSecond\r\n")
        files = self.workspace.prepare(self.owner, self.conversation)
        run = self.root / "crlf-run"
        run.mkdir()
        files.materialize(run)
        observed = WorkspaceFiles.from_workspace(run)
        self.assertEqual(
            observed.files["project/agent-files/notes.md"], "First\r\nSecond\r\n"
        )
        self.workspace.persist(self.owner, self.conversation, observed)
        self.assertEqual(self.notes.read_bytes(), b"First\r\nSecond\r\n")

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
