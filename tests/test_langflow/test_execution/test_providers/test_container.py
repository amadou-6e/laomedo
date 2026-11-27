"""Supervisor races use the real pipe dispatcher task and revoked host receipts."""

import asyncio
from io import BytesIO
from types import SimpleNamespace
import threading
import time
import unittest
from unittest.mock import Mock
from uuid import uuid4

from laomedo.github.node_runs.authority import GitHubRunAuthority
from laomedo.integrations.langflow.execution.providers.container import (
    DockerProviderGraphWorker,
)
from laomedo.integrations.langflow.execution.worker.channel import GraphWorkerChannel
from laomedo.integrations.langflow.execution.worker.errors import GraphWorkerError
from laomedo.integrations.langflow.execution.worker.models import GraphWorkerResult


class ProviderSupervisorTests(unittest.IsolatedAsyncioTestCase):
    """Cancellation drains admitted starts; worker terminal text proves no model run."""

    def worker(self):
        graph = {"nodes": [], "edges": []}
        digest = GitHubRunAuthority.digest_graph(graph)
        node = SimpleNamespace(vertex_id="codex")
        plan = SimpleNamespace(
            profile_id=uuid4(),
            flow_id=uuid4(),
            graph_digest="sha256:" + digest,
            nodes=(node,),
            deadline=time.monotonic() + 60,
        )
        runs = SimpleNamespace(
            settle=Mock(),
            plan=Mock(return_value=plan),
            finish=Mock(return_value=object()),
            resolve=Mock(),
            run_for_vertex=Mock(),
        )
        controllers = SimpleNamespace(
            graph_runs=runs, stop_graph=Mock(return_value=()), graph_native=Mock()
        )
        job = SimpleNamespace(
            job_id=uuid4(),
            flow_id=plan.flow_id,
            graph_digest=digest,
            graph=graph,
            providers=(SimpleNamespace(vertex_id="codex"),),
            public_issues=(),
            private_payload=lambda: {},
        )
        dispatcher = SimpleNamespace(
            observe_node=Mock(),
            plan=plan,
            controllers=controllers,
            capability="host-only",
            graph_digest=plan.graph_digest,
            worker_graph_digest=digest,
            issues={},
        )
        return DockerProviderGraphWorker(None, job, dispatcher), job

    async def test_cancelled_wait_does_not_abandon_a_native_start_thread(self):
        worker, job = self.worker()
        started, release = threading.Event(), threading.Event()
        effects = []

        def start(call):
            started.set()
            release.wait(3)
            effects.append("native-reservation")
            return None

        def cleanup(receipt):
            self.assertTrue(worker._shutdown is receipt)
            effects.append("receipt-cleanup")
            return ()

        worker.dispatcher.request = start
        worker.dispatcher.controllers.stop_graph.side_effect = cleanup
        pending = asyncio.create_task(worker._request(object(), threading.Event()))
        self.assertTrue(await asyncio.to_thread(started.wait, 1))
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        finish = asyncio.create_task(worker._finish_job(job.job_id))
        await asyncio.sleep(0)
        self.assertFalse(finish.done())
        self.assertIsNone(worker._remaining(job.job_id))
        release.set()
        await asyncio.wait_for(finish, 2)
        self.assertEqual(effects, ["native-reservation", "receipt-cleanup"])
        self.assertEqual(worker.dispatcher.controllers.graph_runs.finish.call_count, 1)

    async def test_cleanup_failure_preserves_the_revoked_receipt_for_reconciliation(
        self,
    ):
        worker, job = self.worker()
        worker.dispatcher.controllers.stop_graph.side_effect = OSError("unknown")
        with self.assertRaises(OSError):
            await worker._finish_job(job.job_id)
        receipt = worker._shutdown
        self.assertIsNotNone(receipt)
        self.assertIsNone(worker.stops)
        worker.dispatcher.controllers.stop_graph.side_effect = None
        await worker._finish_job(job.job_id)
        self.assertIs(worker._shutdown, receipt)
        self.assertEqual(worker.dispatcher.controllers.graph_runs.finish.call_count, 1)

    async def test_worker_cannot_claim_completion_without_host_native_records(self):
        worker, job = self.worker()
        worker.dispatcher.controllers.graph_native.return_value.runner.status.return_value = {
            "status": "prepared"
        }
        incoming = asyncio.StreamReader()
        frame = BytesIO()
        GraphWorkerChannel.write_message(
            frame,
            GraphWorkerResult(
                event="completed", job_id=job.job_id, outputs=[]
            ).model_dump(mode="json"),
        )
        incoming.feed_data(frame.getvalue())
        process = SimpleNamespace(
            stdout=incoming, stdin=SimpleNamespace(write=Mock(), drain=self.drain)
        )
        with self.assertRaises(GraphWorkerError):
            await worker._exchange(process, job, threading.Event())

    async def drain(self):
        """Inert pipe writer; actual framing and terminal validation still execute."""

    async def test_graph_substitution_refuses_before_any_container_control(self):
        worker, job = self.worker()
        job.graph = {"nodes": [{"id": "substituted"}], "edges": []}
        with self.assertRaises(GraphWorkerError):
            worker._validate_graph(job)

    async def test_host_selection_and_worker_projection_have_separate_fixed_digests(
        self,
    ):
        worker, job = self.worker()
        worker.plan.graph_digest = "sha256:" + "b" * 64
        self.assertEqual(worker._job_scope(job.job_id).graph_digest, job.graph_digest)
        worker._validate_graph(job)
        job.graph_digest = "c" * 64
        with self.assertRaises(GraphWorkerError):
            worker._validate_graph(job)
