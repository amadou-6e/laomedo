"""Real Flow database round trips for portable files and app-owned settings."""

import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from langflow.services.database.models.flow.model import Flow

from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.storage.files import ProjectStorage
from laomedo.integrations.langflow.assistant.storage.graphs import ProjectGraphs
from laomedo.integrations.langflow.assistant.storage.models import (
    GraphFileRequest,
    RepositoryLocation,
    RepositoryRegistration,
)


class ProjectGraphTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from tests.test_langflow.test_assistant.test_workflows import WorkflowTests

        await WorkflowTests.asyncSetUp(self)
        self.root = Path(self.directory.name)
        (self.root / "repo" / ".git").mkdir(parents=True)
        self.files = ProjectStorage(self.root / "storage")
        self.files.register(
            self.owner,
            RepositoryRegistration(name="Project", path=str(self.root / "repo")),
        )
        repository = self.files.document(self.owner).repositories[0].id
        self.location = RepositoryLocation(
            repository_id=repository, path="graphs/research.json"
        )
        self.runtime = SimpleNamespace(
            project_storage=self.files, store=self.store, check_session=AsyncMock()
        )
        self.graphs = ProjectGraphs(self.runtime)
        saved = await self.workflows.save(self.context, self.request)
        self.graph = UUID(saved["workflow_id"])
        self.catalog_patch = patch(
            "laomedo.integrations.langflow.assistant.storage.graphs.ComponentCatalog.from_installed",
            AsyncMock(return_value=self.catalog),
        )
        self.catalog_patch.start()
        self.addCleanup(self.catalog_patch.stop)
        self.fence_patch = patch(
            "langflow.services.database.models.flow.guards.ensure_flow_update_allowed.laomedo_storage_fence",
            True,
            create=True,
        )
        self.fence_patch.start()
        self.addCleanup(self.fence_patch.stop)

    async def asyncTearDown(self):
        from tests.test_langflow.test_assistant.test_workflows import WorkflowTests

        await WorkflowTests.asyncTearDown(self)

    async def storage_request(self, location=None, digest=None):
        rows = await self.graphs.list(self.owner)
        revision = next(row["revision"] for row in rows if row["id"] == str(self.graph))
        return GraphFileRequest(
            location=location or self.location,
            expected_graph_revision=revision,
            expected_file_hash=digest,
        )

    async def test_save_load_preserves_private_settings_and_node_identity(self):
        async with self.store.transaction() as session:
            flow = await session.get(Flow, self.graph)
            original_id = flow.data["nodes"][0]["id"]
            data = json.loads(json.dumps(flow.data))
            data["nodes"][0]["data"]["node"]["template"]["api_key"][
                "value"
            ] = "PRIVATE_EXISTING_KEY"
            flow.data = data
        result = await self.graphs.sync(
            self.owner, "fixture", self.graph, await self.storage_request()
        )
        path = self.files.graph_path(self.owner, self.location)
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("PRIVATE_EXISTING_KEY", text)
        self.assertNotIn("TRUSTED_CODE", text)
        value = json.loads(text)
        value["spec"]["nodes"][0]["fields"]["text"] = "Changed from repository"
        path.write_text(json.dumps(value), encoding="utf-8")
        observed = self.files.describe(self.owner)["graphs"][str(self.graph)][
            "current_sha256"
        ]
        self.assertNotEqual(observed, result["sha256"])
        await self.graphs.sync(
            self.owner,
            "fixture",
            self.graph,
            await self.storage_request(digest=observed),
            load=True,
        )
        async with self.store.sessions() as session:
            flow = await session.get(Flow, self.graph)
            node = flow.data["nodes"][0]
            self.assertEqual(node["id"], original_id)
            self.assertEqual(
                node["data"]["node"]["template"]["api_key"]["value"],
                "PRIVATE_EXISTING_KEY",
            )
            self.assertEqual(
                node["data"]["node"]["template"]["text"]["value"],
                "Changed from repository",
            )

    async def test_stale_app_and_file_revisions_are_rejected(self):
        request = await self.storage_request()
        await self.graphs.sync(self.owner, "fixture", self.graph, request)
        with self.assertRaisesRegex(AssistantError, "assistant_storage_file_changed"):
            await self.graphs.sync(self.owner, "fixture", self.graph, request)
        path = self.files.graph_path(self.owner, self.location)
        digest = self.files.digest(path)
        with self.assertRaisesRegex(
            AssistantError, "assistant_source_revision_changed"
        ):
            await self.graphs.sync(
                self.owner,
                "fixture",
                self.graph,
                request.model_copy(
                    update={
                        "expected_graph_revision": "sha256:stale",
                        "expected_file_hash": digest,
                    }
                ),
                load=True,
            )

    async def test_two_graph_locations_survive_storage_restart(self):
        await self.graphs.sync(
            self.owner, "fixture", self.graph, await self.storage_request()
        )
        second = await self.workflows.save(
            self.context,
            self.request.model_copy(
                update={"draft_key": "second", "name": "Second graph"}
            ),
        )
        second_id = UUID(second["workflow_id"])
        location = self.location.model_copy(update={"path": "graphs/second.json"})
        await self.graphs.sync(
            self.owner,
            "fixture",
            second_id,
            GraphFileRequest(
                location=location, expected_graph_revision=second["revision"]
            ),
        )
        restarted = ProjectStorage(self.root / "storage")
        bindings = restarted.document(self.owner).graphs
        self.assertEqual(
            bindings[str(self.graph)].location.path, "graphs/research.json"
        )
        self.assertEqual(bindings[str(second_id)].location.path, "graphs/second.json")
        self.assertNotEqual(
            restarted.graph_path(self.owner, bindings[str(self.graph)].location),
            restarted.graph_path(self.owner, bindings[str(second_id)].location),
        )

    async def test_empty_editor_canvas_round_trips(self):
        async with self.store.transaction() as session:
            flow = await session.get(Flow, self.graph)
            flow.data = {"nodes": [], "edges": []}
        saved = await self.graphs.sync(
            self.owner, "fixture", self.graph, await self.storage_request()
        )
        await self.graphs.sync(
            self.owner,
            "fixture",
            self.graph,
            await self.storage_request(digest=saved["sha256"]),
            load=True,
        )
        async with self.store.sessions() as session:
            flow = await session.get(Flow, self.graph)
            self.assertEqual(flow.data["nodes"], [])
            self.assertTrue(flow.data["laomedo_storage_revision"])

    async def test_loading_refuses_an_installation_without_the_editor_fence(self):
        with patch(
            "langflow.services.database.models.flow.guards.ensure_flow_update_allowed.laomedo_storage_fence",
            False,
        ):
            with self.assertRaisesRegex(
                AssistantError, "assistant_storage_editor_fence_missing"
            ):
                await self.graphs.sync(
                    self.owner,
                    "fixture",
                    self.graph,
                    await self.storage_request(),
                    load=True,
                )
        self.assertFalse(self.files.graph_path(self.owner, self.location).exists())

    async def test_wrong_owner_locked_and_invalid_files_preserve_graph(self):
        request = await self.storage_request()
        with self.assertRaises(AssistantError):
            await self.graphs.sync(uuid4(), "fixture", self.graph, request)
        await self.graphs.sync(self.owner, "fixture", self.graph, request)
        path = self.files.graph_path(self.owner, self.location)
        path.write_text('{"invalid": true}', encoding="utf-8")
        with self.assertRaisesRegex(AssistantError, "assistant_storage_graph_invalid"):
            await self.graphs.sync(
                self.owner,
                "fixture",
                self.graph,
                await self.storage_request(digest=self.files.digest(path)),
                load=True,
            )
        async with self.store.transaction() as session:
            flow = await session.get(Flow, self.graph)
            self.assertEqual(
                flow.data["nodes"][0]["data"]["node"]["template"]["text"]["value"],
                "Hello",
            )
            flow.locked = True
        with self.assertRaisesRegex(AssistantError, "assistant_storage_graph_locked"):
            await self.graphs.sync(
                self.owner,
                "fixture",
                self.graph,
                await self.storage_request(digest=self.files.digest(path)),
                load=True,
            )
