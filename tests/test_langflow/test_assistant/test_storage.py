"""Persistent project bindings, bounded file tools and stale-write protection."""

from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.storage.files import ProjectStorage
from laomedo.integrations.langflow.assistant.storage.models import (
    AgentFileWrite,
    RepositoryLocation,
    RepositoryRegistration,
)


class ProjectStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.checkout = self.root / "repo"
        (self.checkout / ".git").mkdir(parents=True)
        self.owner = uuid4()
        self.files = ProjectStorage(self.root / "state")
        self.files.register(
            self.owner, RepositoryRegistration(name="Project", path=str(self.checkout))
        )
        self.repository = self.files.document(self.owner).repositories[0].id
        self.location = RepositoryLocation(
            repository_id=self.repository, path="agent-files"
        )
        self.files.configure_agent_files(self.owner, self.location)

    def test_persistent_files_and_profile_scoped_selections(self):
        written = self.files.write_file(
            self.owner, AgentFileWrite(path="notes/plan.md", content="Persistent plan")
        )
        restarted = ProjectStorage(self.root / "state")
        self.assertEqual(
            restarted.read_file(self.owner, "notes/plan.md")["content"],
            "Persistent plan",
        )
        self.assertEqual(
            restarted.list_files(self.owner)["agent_files"], ["notes/plan.md"]
        )
        self.assertEqual(restarted.describe(uuid4())["repositories"], [])
        with self.assertRaises(AssistantError):
            restarted.read_file(uuid4(), "notes/plan.md")
        restarted.write_file(
            self.owner,
            AgentFileWrite(
                path="notes/plan.md",
                content="Updated",
                expected_sha256=written["sha256"],
            ),
        )
        self.assertEqual(
            restarted.read_file(self.owner, "notes/plan.md")["content"], "Updated"
        )

    def test_stale_and_absent_conditions_preserve_existing_file(self):
        request = AgentFileWrite(path="plan.md", content="First")
        self.files.write_file(self.owner, request)
        with self.assertRaisesRegex(AssistantError, "assistant_storage_file_changed"):
            self.files.write_file(
                self.owner, request.model_copy(update={"content": "Overwritten"})
            )
        self.assertEqual(
            self.files.read_file(self.owner, "plan.md")["content"], "First"
        )

    def test_escaping_private_and_platform_paths_are_refused(self):
        for path in (
            "../escape",
            "/absolute",
            "x/../../escape",
            ".git/config",
            ".env",
            "x/.env.local",
            "x/auth.json",
            "x\\escape",
            "C:escape",
            "x//escape",
            "x/.. /escape",
        ):
            with self.subTest(path=path), self.assertRaises(AssistantError):
                self.files.write_file(
                    self.owner, AgentFileWrite(path=path, content="denied")
                )
        self.assertFalse((self.root / "escape").exists())

    def test_graph_and_agent_locations_cannot_overlap(self):
        with self.assertRaisesRegex(
            AssistantError, "assistant_storage_location_conflict"
        ):
            self.files.graph_path(
                self.owner,
                RepositoryLocation(
                    repository_id=self.repository, path="agent-files/graph.json"
                ),
            )
        graph = uuid4()
        location = RepositoryLocation(
            repository_id=self.repository, path="graphs/research.json"
        )
        path = self.files.graph_path(self.owner, location)
        self.files.replace(path, b"{}")
        self.files.bind_graph(self.owner, graph, location, self.files.digest(path))
        with self.assertRaisesRegex(
            AssistantError, "assistant_storage_location_conflict"
        ):
            self.files.configure_agent_files(
                self.owner,
                RepositoryLocation(repository_id=self.repository, path="graphs"),
            )
        # A changed file is observable on refresh rather than permanently stuck on its old hash.
        self.files.replace(path, b'{"changed": true}')
        binding = self.files.describe(self.owner)["graphs"][str(graph)]
        self.assertNotEqual(binding["sha256"], binding["current_sha256"])

    def test_removed_checkout_does_not_fall_back_to_another_location(self):
        (self.checkout / ".git").rmdir()
        with self.assertRaisesRegex(
            AssistantError, "assistant_storage_repository_unavailable"
        ):
            self.files.write_file(
                self.owner, AgentFileWrite(path="plan.md", content="Denied")
            )

    def test_links_are_refused_when_supported(self):
        outside = self.root / "outside"
        outside.mkdir()
        link = self.checkout / "agent-files" / "outside"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks requires Windows privilege")
        with self.assertRaises(AssistantError):
            self.files.write_file(
                self.owner, AgentFileWrite(path="outside/escape.md", content="Denied")
            )
