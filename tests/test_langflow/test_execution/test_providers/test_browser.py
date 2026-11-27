"""Real canvas HTTP/protocol boundary with inert execution; no model acceptance."""

import asyncio
import socket
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from langflow.services.auth.utils import get_current_active_user

from laomedo.integrations.langflow.execution.providers.browser import (
    ProviderCanvasRoutes,
)
from laomedo.integrations.langflow.execution.providers.models import (
    ProviderCanvasJob,
    ProviderWorkerEvent,
)
from lfx.workflow.adapters import StreamAdapterContext, get_stream_adapter
from laomedo.integrations.langflow.execution.providers.settings import (
    PROVIDER_PROGRESS_QUEUE_SIZE,
)


class ProviderCanvasTests(unittest.IsolatedAsyncioTestCase):
    """Ownership, run policy and native AG-UI framing survive the isolated adapter."""

    def setUp(self):
        self.owner = SimpleNamespace(id=uuid4())
        self.executor = SimpleNamespace(
            browser=Mock(), execute=AsyncMock(side_effect=self.execute)
        )
        self.routes = ProviderCanvasRoutes("http://127.0.0.1:17885", self.executor)
        self.routes.snapshot = AsyncMock(
            return_value=SimpleNamespace(
                id=uuid4(), data={"nodes": [{"id": "text"}], "edges": []}
            )
        )
        self.app = FastAPI()
        self.app.dependency_overrides[get_current_active_user] = self.authenticated
        self.routes.install(self.app)

    async def authenticated(self):
        return self.owner

    async def execute(self, snapshot, action, actor, run_id, *, on_event=None):
        on_event(ProviderWorkerEvent(event="build_start", data={"id": "text"}))
        on_event(
            ProviderWorkerEvent(
                event="end_vertex",
                data={
                    "build_data": {
                        "id": "text",
                        "valid": True,
                        "data": {"results": {"text": "Actual fixture output"}},
                    }
                },
            )
        )
        return object()

    def client(self, *, origin="http://127.0.0.1:17885"):
        return AsyncClient(
            transport=ASGITransport(app=self.app),
            base_url="http://127.0.0.1:17885",
            headers={"Origin": origin},
        )

    def payload(self, **extra):
        return {
            "flow_id": str(uuid4()),
            "mode": "stream",
            "stream_protocol": "agui",
            **extra,
        }

    async def test_existing_canvas_protocol_streams_actual_progress_and_cleans_task(
        self,
    ):
        async with self.client() as client:
            response = await client.post("/api/v2/workflows", json=self.payload())
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])
        self.assertIn('"type":"RUN_STARTED"', response.text)
        self.assertIn('"type":"STEP_FINISHED"', response.text)
        self.assertIn("Actual fixture output", response.text)
        self.assertIn('"type":"RUN_FINISHED"', response.text)
        self.executor.execute.assert_awaited_once()
        self.assertEqual(self.routes.jobs, {})

    async def test_refused_modes_overrides_and_foreign_origin_never_dispatch(self):
        for fields in (
            {"globals": {"secret": "fixture"}},
            {"mode": "background"},
            {"tweaks": {"node": {"code": "not executed"}}},
            {"files": ["host-file"]},
        ):
            async with self.client() as client:
                response = await client.post(
                    "/api/v2/workflows", json=self.payload(**fields)
                )
            self.assertEqual(response.status_code, 422)
        async with self.client(origin="http://foreign.example") as client:
            response = await client.post("/api/v2/workflows", json=self.payload())
        self.assertEqual(response.status_code, 403)
        self.executor.execute.assert_not_awaited()
        self.routes.snapshot.assert_not_awaited()

    async def test_stop_cannot_cancel_another_owners_task(self):
        identifier = uuid4()
        task = asyncio.create_task(asyncio.sleep(30))
        self.routes.jobs[identifier] = ProviderCanvasJob(owner_id=uuid4(), task=task)
        try:
            async with self.client() as client:
                response = await client.post(
                    "/api/v2/workflows/stop", json={"job_id": str(identifier)}
                )
            self.assertEqual(response.status_code, 404)
            self.assertFalse(task.cancelling())
            self.routes.jobs[identifier] = ProviderCanvasJob(
                owner_id=self.owner.id, task=task
            )
            async with self.client() as client:
                response = await client.post(
                    "/api/v2/workflows/stop", json={"job_id": str(identifier)}
                )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(task.cancelling())
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_disconnected_stream_waits_for_its_execution_cleanup(self):
        entered, cleaned = asyncio.Event(), asyncio.Event()

        async def execute(*args, **kwargs):
            entered.set()
            try:
                await asyncio.Future()
            finally:
                await asyncio.sleep(0)
                cleaned.set()

        self.executor.execute.side_effect = execute
        identifier = uuid4()
        adapter = get_stream_adapter(
            "agui",
            StreamAdapterContext(run_id=str(identifier), thread_id=str(identifier)),
        )
        snapshot = self.routes.snapshot.return_value
        events = self.routes.events(snapshot, object(), self.owner, identifier, adapter)
        await anext(events)
        await entered.wait()
        await events.aclose()
        self.assertTrue(cleaned.is_set())
        self.assertEqual(self.routes.jobs, {})

    async def test_stalled_observer_drops_progress_without_aborting_execution(self):
        completed = asyncio.Event()

        async def execute(*args, on_event=None):
            for _ in range(PROVIDER_PROGRESS_QUEUE_SIZE + 10):
                on_event(ProviderWorkerEvent(event="build_start", data={"id": "text"}))
            completed.set()
            return object()

        self.executor.execute.side_effect = execute
        identifier = uuid4()
        adapter = get_stream_adapter(
            "agui",
            StreamAdapterContext(run_id=str(identifier), thread_id=str(identifier)),
        )
        events = self.routes.events(
            self.routes.snapshot.return_value, object(), self.owner, identifier, adapter
        )
        await anext(events)
        task = self.routes.jobs[identifier].task
        await asyncio.wait_for(completed.wait(), 2)
        await task
        frames = b"".join([frame async for frame in events]).decode()
        self.assertIn('"type":"RUN_FINISHED"', frames)
        self.assertNotIn('"type":"RUN_ERROR"', frames)
        self.assertIn("dropped_updates", frames)
        self.assertEqual(self.routes.jobs, {})

    async def test_real_uvicorn_disconnect_releases_task_and_receipt(self):
        import uvicorn

        entered, cleaned = asyncio.Event(), asyncio.Event()

        async def execute(*args, **kwargs):
            entered.set()
            try:
                await asyncio.Future()
            finally:
                await asyncio.sleep(0)
                cleaned.set()

        self.executor.execute.side_effect = execute
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        self.routes.origin = "http://127.0.0.1:" + str(listener.getsockname()[1])
        server = uvicorn.Server(
            uvicorn.Config(self.app, log_config=None, access_log=False, lifespan="off")
        )
        serving = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            deadline = time.monotonic() + 5
            while not server.started:
                self.assertLess(time.monotonic(), deadline)
                await asyncio.sleep(0.01)
            async with AsyncClient(
                base_url=self.routes.origin,
                trust_env=False,
                headers={"Origin": self.routes.origin},
            ) as client:
                async with client.stream(
                    "POST", "/api/v2/workflows", json=self.payload()
                ) as response:
                    self.assertEqual(response.status_code, 200)
                    async for line in response.aiter_lines():
                        if "RUN_STARTED" in line:
                            break
                    await asyncio.wait_for(entered.wait(), 2)
            await asyncio.wait_for(cleaned.wait(), 3)
            await asyncio.sleep(0)
            self.assertEqual(self.routes.jobs, {})
        finally:
            server.should_exit = True
            await asyncio.wait_for(serving, 5)
            listener.close()

    def test_component_run_includes_only_the_selected_upstream_subgraph(self):
        graph = {
            "nodes": [
                {"id": value} for value in ("issue", "codex", "claude", "downstream")
            ],
            "edges": [
                {"source": "issue", "target": "codex"},
                {"source": "codex", "target": "claude"},
                {"source": "claude", "target": "downstream"},
            ],
        }
        selected = self.routes.through(graph, "claude")
        self.assertEqual(
            [node["id"] for node in selected["nodes"]], ["issue", "codex", "claude"]
        )
        self.assertEqual(len(selected["edges"]), 2)
        self.assertEqual(len(graph["nodes"]), 4)
