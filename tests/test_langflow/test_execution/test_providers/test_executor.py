"""Broker dispatch/replay tests with synthetic worker replies, never model acceptance."""

from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from langflow.services.auth.context import (
    AuthCredentialContext,
    get_current_auth_context,
    set_current_auth_context,
)

from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.connections.models import BrowserProviderSession
from laomedo.integrations.langflow.execution.providers.executor import (
    ProviderGraphExecutor,
)
from laomedo.integrations.langflow.execution.worker.models import GraphWorkerResult
from laomedo.integrations.langflow.provider_connections.bindings import (
    ProviderGraphBindings,
)


class ProviderExecutorTests(unittest.IsolatedAsyncioTestCase):
    """Only a verified owner can reach one durable job and its isolated worker."""

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.owner, self.flow, self.job_id = uuid4(), uuid4(), uuid4()
        self.controllers = SimpleNamespace(
            service=Mock(), graph_runs=Mock(), finish_graph=Mock()
        )
        self.executor = ProviderGraphExecutor(
            None, SimpleNamespace(admission=Mock()), self.controllers
        )
        browser = BrowserProviderSession(profile_id=self.owner, lease_hash="lease")
        marker = ProviderGraphBindings.session.set(browser)
        self.addCleanup(ProviderGraphBindings.session.reset, marker)
        previous = get_current_auth_context()
        set_current_auth_context(AuthCredentialContext(method="jwt"))
        self.addCleanup(set_current_auth_context, previous)
        self.stack.enter_context(
            patch.object(ProviderGraphBindings, "service", self.controllers.service)
        )
        self.jobs = SimpleNamespace(
            create_job=AsyncMock(),
            update_job_status=AsyncMock(),
            update_job_metadata=AsyncMock(),
        )
        self.stack.enter_context(
            patch("langflow.services.deps.get_job_service", return_value=self.jobs)
        )
        self.dispatcher = SimpleNamespace(
            node_outcomes={"codex": {"node_id": "codex", "state": "succeeded"}}
        )
        self.stack.enter_context(
            patch(
                "laomedo.integrations.langflow.execution.providers.executor.ProviderGraphDispatcher",
                return_value=self.dispatcher,
            )
        )
        self.worker = SimpleNamespace(
            stops=(SimpleNamespace(settled=True, cancel_confirmed=False),),
            run=AsyncMock(
                return_value=GraphWorkerResult(
                    event="completed",
                    job_id=self.job_id,
                    outputs=[{"inputs": {}, "outputs": []}],
                )
            ),
        )
        self.worker_factory = self.stack.enter_context(
            patch(
                "laomedo.integrations.langflow.execution.providers.executor.DockerProviderGraphWorker",
                return_value=self.worker,
            )
        )
        self.prepared = SimpleNamespace(
            plan=SimpleNamespace(graph_digest="sha256:" + "a" * 64),
            job=Mock(),
            issues=(),
        )
        self.executor.admission.prepare = Mock(return_value=self.prepared)
        self.executor._public_gateway = Mock(return_value=object())
        self.snapshot = SimpleNamespace(id=self.flow, user_id=self.owner, data={})
        self.actor = SimpleNamespace(id=self.owner)
        self.request = SimpleNamespace(input_value="", output_component=None)

    async def test_native_job_barrier_precedes_worker_and_keeps_existing_response_shape(
        self,
    ):
        response = await self.executor.execute(
            self.snapshot, self.request, self.actor, str(self.job_id)
        )
        self.assertEqual(response.session_id, str(self.job_id))
        self.jobs.create_job.assert_awaited_once()
        self.assertEqual(self.jobs.create_job.call_args.kwargs["user_id"], self.owner)
        self.assertEqual(self.jobs.create_job.call_args.args, (self.job_id, self.flow))
        self.worker.run.assert_awaited_once()
        metadata = self.jobs.update_job_metadata.call_args.args[1]
        self.assertEqual(
            metadata["isolated_provider_nodes"],
            [{"node_id": "codex", "state": "succeeded"}],
        )
        self.assertTrue(metadata["native_cleanup_confirmed"])
        self.assertEqual(self.executor.workers, {})
        self.assertEqual(self.executor.uncertain, {})

    async def test_existing_job_is_not_replayed_or_admitted_to_provider_authority(self):
        self.jobs.create_job.side_effect = RuntimeError("duplicate job UUID")
        with self.assertRaises(RuntimeError):
            await self.executor.execute(
                self.snapshot, self.request, self.actor, str(self.job_id)
            )
        self.worker_factory.assert_not_called()
        self.controllers.graph_runs.admit.assert_not_called()
        self.assertEqual(self.executor.workers, {})

    async def test_foreign_owner_api_key_and_missing_session_cannot_reach_worker(self):
        with self.assertRaises(ProviderConnectionError):
            await self.executor.execute(
                self.snapshot,
                self.request,
                SimpleNamespace(id=uuid4()),
                str(self.job_id),
            )
        set_current_auth_context(AuthCredentialContext(method="api_key"))
        with self.assertRaises(ProviderConnectionError):
            self.executor.browser(self.owner)
        set_current_auth_context(AuthCredentialContext(method="jwt"))
        marker = ProviderGraphBindings.session.set(None)
        try:
            with self.assertRaises(ProviderConnectionError):
                self.executor.browser(self.owner)
        finally:
            ProviderGraphBindings.session.reset(marker)
        self.worker_factory.assert_not_called()
        self.jobs.create_job.assert_not_awaited()

    async def test_unconfirmed_cleanup_is_retained_and_never_reported_confirmed(self):
        self.worker.stops = None
        await self.executor.execute(
            self.snapshot, self.request, self.actor, str(self.job_id)
        )
        self.assertIs(self.executor.uncertain[self.job_id], self.worker)
        self.assertFalse(
            self.jobs.update_job_metadata.call_args.args[1]["native_cleanup_confirmed"]
        )
