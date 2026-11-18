"""Worker dispatch and revocation invariants with synthetic provider reads only."""

import unittest
from uuid import uuid4

from pydantic import SecretStr, ValidationError

from laomedo.github.node_runs.errors import GitHubNodeAuthorizationError
from laomedo.github.node_runs.models import (
    GitHubNodeReadResult,
    GitHubNodeSelection,
    GitHubWorkerReadRequest,
)
from laomedo.github.node_runs.authority import GitHubRunAuthority
from laomedo.github.node_runs.worker_access import GitHubWorkerAccess
from test_github.test_node_runs.test_authority import NodeConnectionFixture


class WorkerReadFixture:
    """Observe derived provider inputs and optionally revoke before response release."""

    def __init__(self, authority):
        self.authority = authority
        self.calls = []
        self.revoke_job = None

    async def read(self, scope, connection_id, **values):
        await scope.revalidate()
        authorization = await self.authority.connections.authorize_read(
            scope, connection_id, 12
        )
        self.calls.append((scope.owner_id, connection_id, values))
        if self.revoke_job is not None:
            self.authority.revoke_worker(self.revoke_job)
        return GitHubNodeReadResult(
            authorization=authorization, payload={"synthetic": "private issue text"}
        )


class GitHubWorkerAccessTests(unittest.IsolatedAsyncioTestCase):
    """The worker never chooses a credential scope or broadens its picker target."""

    async def asyncSetUp(self):
        self.connections = NodeConnectionFixture()
        self.authority = GitHubRunAuthority(self.connections)
        self.job = uuid4()
        flow = uuid4()
        graph = {"nodes": [], "edges": []}
        selection = GitHubNodeSelection(
            vertex_id="issue-1",
            kind="issue",
            connection_id=self.connections.connection,
            repository=self.connections.repository,
            number=7,
        )
        reference, _ = await self.authority.prepare(
            self.connections.scope(), flow, graph, [selection]
        )
        await self.authority.admit(
            reference,
            self.connections.scope(),
            flow_id=flow,
            graph=graph,
            job_id=self.job,
            approved=False,
        )
        self.capability = self.authority.issue_worker(
            self.job, deadline=self.authority.clock() + 60.0
        )
        self.reader = WorkerReadFixture(self.authority)
        self.access = GitHubWorkerAccess(self.authority, self.reader)
        self.request = GitHubWorkerReadRequest(
            job_id=self.job, vertex_id="issue-1", labels=[], state="open"
        )

    async def test_credential_bounds_and_target_are_derived_from_broker_selection(self):
        result = await self.access.inspect(self.capability, self.request)
        self.assertEqual(result, {"synthetic": "private issue text"})
        self.assertEqual(
            self.reader.calls,
            [
                (
                    self.connections.owner,
                    self.connections.connection,
                    dict(
                        kind="issue",
                        action="inspect",
                        repository_url="https://github.com/synthetic/private",
                        labels=[],
                        state="open",
                        number=7,
                    ),
                )
            ],
        )
        self.assertNotIn(self.capability.get_secret_value(), str(result))

    def test_wire_input_cannot_replace_account_repository_or_operation(self):
        for name, value in (
            ("owner_id", str(uuid4())),
            ("connection_id", str(uuid4())),
            ("repository_url", "https://github.com/other/private"),
            ("operation", {"action": "close"}),
            ("grant_ref", "arbitrary"),
        ):
            with self.assertRaises(ValidationError):
                GitHubWorkerReadRequest.model_validate(
                    {**self.request.model_dump(), name: value}
                )

    async def test_missing_worker_authority_never_dispatches_a_provider_read(self):
        with self.assertRaises(GitHubNodeAuthorizationError):
            await self.access.inspect(SecretStr("x" * 43), self.request)
        self.assertEqual(self.reader.calls, [])

    async def test_runtime_reference_cannot_replace_a_picker_target(self):
        request = self.request.model_copy(update={"number": 9})
        with self.assertRaises(GitHubNodeAuthorizationError):
            await self.access.inspect(self.capability, request)
        self.assertEqual(self.reader.calls, [])

    async def test_read_reference_without_picker_stays_within_admitted_repository(self):
        run = self.authority.runs[self.authority.jobs[self.job]]
        selection = run.nodes[0].selection.model_copy(update={"number": None})
        flow, job = uuid4(), uuid4()
        graph = {"nodes": [], "edges": []}
        reference, _ = await self.authority.prepare(
            self.connections.scope(), flow, graph, [selection]
        )
        await self.authority.admit(
            reference,
            self.connections.scope(),
            flow_id=flow,
            graph=graph,
            job_id=job,
            approved=False,
        )
        capability = self.authority.issue_worker(
            job, deadline=self.authority.clock() + 60.0
        )
        request = self.request.model_copy(update={"job_id": job, "number": 9})
        await self.access.inspect(capability, request)
        self.assertEqual(self.reader.calls[0][2]["number"], 9)
        self.assertEqual(self.reader.calls[0][1], self.connections.connection)
        self.assertEqual(
            self.reader.calls[0][2]["repository_url"],
            "https://github.com/synthetic/private",
        )

    async def test_revocation_during_read_prevents_private_payload_release(self):
        self.reader.revoke_job = self.job
        with self.assertRaises(GitHubNodeAuthorizationError):
            await self.access.inspect(self.capability, self.request)
        self.assertEqual(len(self.reader.calls), 1)

    async def test_finished_job_cannot_start_another_read(self):
        self.authority.finish_job(self.job)
        with self.assertRaises(GitHubNodeAuthorizationError):
            await self.access.inspect(self.capability, self.request)
        self.assertEqual(self.reader.calls, [])
