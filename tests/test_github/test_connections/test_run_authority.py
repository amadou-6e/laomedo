"""Run admission invariants with synthetic custody; not live GitHub acceptance."""

import unittest
from uuid import uuid4

from pydantic import SecretStr, ValidationError

from laomedo.github.connections.errors import GitHubNodeAuthorizationError
from laomedo.github.connections.models import (
    GitHubConnectionScope,
    GitHubNodeSelection,
    GitHubReadAuthorization,
    GitHubPrincipal,
    GitHubRepositoryIdentity,
)
from laomedo.github.connections.run_authority import GitHubRunAuthority


class NodeConnectionFixture:
    """Expose a single selected connection and observable online admissions."""

    def __init__(self):
        self.owner = uuid4()
        self.connection = uuid4()
        self.repository = GitHubRepositoryIdentity(
            id=12, full_name="synthetic/private", private=True
        )
        self.principal = GitHubPrincipal(id=34, login="synthetic")
        self.generation = 1
        self.state = "ready"
        self.repositories = (self.repository,)
        self.revoked_lease = False
        self.reads = 0
        self.journal = self

    async def check(self):
        if self.revoked_lease:
            raise GitHubNodeAuthorizationError()

    def scope(self, *, owner=None, lease="lease-one"):
        return GitHubConnectionScope(
            owner_id=owner or self.owner,
            lease_binding=SecretStr(lease),
            check=self.check,
        )

    def get(self, owner, connection):
        return self if owner == self.owner and connection == self.connection else None

    def run_generation_current(self, owner, connection, generation, repository):
        return (
            self.get(owner, connection) is not None
            and self.state == "ready"
            and generation == self.generation
            and repository in self.repositories
        )

    async def authorize_read(self, scope, connection, repository):
        await scope.revalidate()
        self.reads += 1
        if (
            self.get(scope.owner_id, connection) is None
            or repository != 12
            or self.state != "ready"
        ):
            raise GitHubNodeAuthorizationError()
        return GitHubReadAuthorization(
            owner_id=self.owner,
            connection_id=self.connection,
            generation=self.generation,
            repository=self.repository,
            principal=self.principal,
            deadline=60,
        )


class GitHubRunAuthorityTests(unittest.IsolatedAsyncioTestCase):
    """An approved exact job remains dependent on its initiating lease and generation."""

    def setUp(self):
        self.connections = NodeConnectionFixture()
        self.now = 0.0
        self.authority = GitHubRunAuthority(self.connections, clock=lambda: self.now)
        self.scope = self.connections.scope()
        self.flow = uuid4()
        self.job = uuid4()
        self.graph = {"nodes": [{"id": "pr-1"}], "edges": []}
        self.selection = GitHubNodeSelection(
            vertex_id="pr-1",
            kind="pr",
            connection_id=self.connections.connection,
            repository=self.connections.repository,
            number=5,
            operations=("modify", "close"),
        )

    async def prepare(self, selection=None):
        return await self.authority.prepare(
            self.scope, self.flow, self.graph, [selection or self.selection]
        )

    async def admit(self, reference, **changes):
        values = dict(
            flow_id=self.flow, graph=self.graph, job_id=self.job, approved=True
        )
        values.update(changes)
        return await self.authority.admit(reference, self.scope, **values)

    async def resolve(self, reference, **changes):
        values = dict(
            job_id=self.job,
            vertex_id="pr-1",
            connection_id=self.connections.connection,
            repository="synthetic/private",
        )
        values.update(changes)
        return await self.authority._resolve(reference, **values)

    async def test_prepare_does_not_admit_and_write_approval_is_one_use(self):
        reference, nodes = await self.prepare()
        self.assertEqual(nodes[0].selection.operations, ("modify", "close"))
        with self.assertRaises(GitHubNodeAuthorizationError):
            await self.resolve(reference)
        await self.admit(reference)
        self.assertEqual((await self.resolve(reference))[0].generation, 1)
        with self.assertRaises(GitHubNodeAuthorizationError):
            await self.admit(reference)
        self.assertEqual(self.connections.reads, 2)

    async def test_worker_requires_separate_capability_not_plan_or_job_identity(self):
        reference, _ = await self.prepare()
        with self.assertRaises(GitHubNodeAuthorizationError):
            self.authority.issue_worker(self.job)
        await self.admit(reference)
        capability = self.authority.issue_worker(self.job)
        self.assertNotEqual(capability.get_secret_value(), reference)
        with self.assertRaises(GitHubNodeAuthorizationError):
            self.authority.issue_worker(self.job)
        for supplied in (
            SecretStr(reference),
            SecretStr("x" * 43),
            capability.get_secret_value(),
        ):
            with self.assertRaises(GitHubNodeAuthorizationError):
                await self.authority.resolve_worker(
                    supplied, job_id=self.job, vertex_id="pr-1"
                )
        authorization, selection = await self.authority.resolve_worker(
            capability, job_id=self.job, vertex_id="pr-1"
        )
        self.assertEqual(authorization.repository, self.connections.repository)
        self.assertEqual(selection, self.selection)
        self.assertNotIn(capability.get_secret_value(), repr(self.authority.workers))
        self.assertNotIn(capability.get_secret_value(), repr(capability))

    async def test_worker_cannot_select_another_job_or_vertex(self):
        reference, _ = await self.prepare()
        await self.admit(reference)
        capability = self.authority.issue_worker(self.job)
        for job, vertex in ((uuid4(), "pr-1"), (self.job, "other")):
            with self.assertRaises(GitHubNodeAuthorizationError):
                await self.authority.resolve_worker(
                    capability, job_id=job, vertex_id=vertex
                )
        self.assertEqual(self.connections.reads, 1)

    async def test_revoked_worker_stops_access_and_replacement_does_not_restore_old_key(
        self,
    ):
        reference, _ = await self.prepare()
        await self.admit(reference)
        capability = self.authority.issue_worker(self.job)
        self.authority.revoke_worker(self.job)
        replacement = self.authority.issue_worker(self.job)
        with self.assertRaises(GitHubNodeAuthorizationError):
            await self.authority.resolve_worker(
                capability, job_id=self.job, vertex_id="pr-1"
            )
        await self.authority.resolve_worker(
            replacement, job_id=self.job, vertex_id="pr-1"
        )
        self.authority.finish_job(self.job)
        self.assertEqual(self.authority.workers, {})
        with self.assertRaises(GitHubNodeAuthorizationError):
            await self.authority.resolve_worker(
                replacement, job_id=self.job, vertex_id="pr-1"
            )

    async def test_worker_lease_and_connection_revalidation_remain_mandatory(self):
        reference, _ = await self.prepare()
        await self.admit(reference)
        capability = self.authority.issue_worker(self.job)
        self.connections.revoked_lease = True
        with self.assertRaises(GitHubNodeAuthorizationError):
            await self.authority.resolve_worker(
                capability, job_id=self.job, vertex_id="pr-1"
            )
        self.connections.revoked_lease = False
        self.connections.generation = 2
        with self.assertRaises(GitHubNodeAuthorizationError):
            await self.authority.resolve_worker(
                capability, job_id=self.job, vertex_id="pr-1"
            )

    async def test_admission_uses_trusted_job_scope_instead_of_preparation_callback(
        self,
    ):
        reference, _ = await self.prepare()
        job_scope = self.connections.scope()
        run = await self.authority.admit(
            reference,
            job_scope,
            flow_id=self.flow,
            graph=self.graph,
            job_id=self.job,
            approved=True,
        )
        self.assertIs(run.scope, job_scope)
        self.assertIsNot(run.scope, self.scope)

    async def test_changes_cancel_expiry_and_missing_approval_cannot_start_job(self):
        for changes in (
            {"flow_id": uuid4()},
            {"graph": {"nodes": [{"id": "other"}], "edges": []}},
            {"approved": False},
            {"job_id": uuid4()},
        ):
            reference, _ = await self.prepare()
            if "job_id" in changes:
                self.now += 301
            with self.assertRaises(GitHubNodeAuthorizationError):
                await self.admit(reference, **changes)
            with self.assertRaises(GitHubNodeAuthorizationError):
                await self.admit(reference)
        self.assertEqual(self.authority.runs, {})

    async def test_wrong_owner_or_lease_does_not_consume_another_profiles_plan(self):
        reference, _ = await self.prepare()
        for scope in (
            self.connections.scope(owner=uuid4()),
            self.connections.scope(lease="other"),
        ):
            with self.assertRaises(GitHubNodeAuthorizationError):
                await self.authority.admit(
                    reference,
                    scope,
                    flow_id=self.flow,
                    graph=self.graph,
                    job_id=self.job,
                    approved=True,
                )
        await self.admit(reference)

    async def test_wrong_job_vertex_account_or_repository_never_reaches_credential_authorization(
        self,
    ):
        reference, _ = await self.prepare()
        await self.admit(reference)
        for changes in (
            {"job_id": uuid4()},
            {"vertex_id": "other"},
            {"connection_id": uuid4()},
            {"repository": "other/private"},
        ):
            with self.assertRaises(GitHubNodeAuthorizationError):
                await self.resolve(reference, **changes)
        self.assertEqual(self.connections.reads, 1)

    async def test_reconnect_revocation_lease_end_and_finished_job_stop_new_access(
        self,
    ):
        for mutation in ("generation", "state", "lease", "finish"):
            self.connections.generation = 1
            self.connections.state = "ready"
            self.connections.revoked_lease = False
            self.job = uuid4()
            reference, _ = await self.prepare()
            await self.admit(reference)
            if mutation == "generation":
                self.connections.generation = 2
            elif mutation == "state":
                self.connections.state = "revoked"
            elif mutation == "lease":
                self.connections.revoked_lease = True
            else:
                self.authority.finish(reference)
            with self.assertRaises(GitHubNodeAuthorizationError):
                await self.resolve(reference)

    async def test_read_only_run_needs_no_write_approval_and_run_reference_cannot_be_serialized(
        self,
    ):
        reference, _ = await self.prepare(
            self.selection.model_copy(update={"operations": ()})
        )
        run = await self.admit(reference, approved=False)
        payload = run.model_dump_json()
        self.assertNotIn(reference, payload)
        self.assertNotIn("lease-one", payload)
        self.assertNotIn("scope", run.model_dump())
        self.assertEqual((await self.resolve(reference))[1].operations, ())
        restarted = GitHubRunAuthority(self.connections)
        with self.assertRaises(GitHubNodeAuthorizationError):
            await restarted._resolve(
                reference,
                job_id=self.job,
                vertex_id="pr-1",
                connection_id=self.connections.connection,
                repository="synthetic/private",
            )

    def test_modify_without_exact_target_is_refused(self):
        with self.assertRaises(ValidationError):
            GitHubNodeSelection(**{**self.selection.model_dump(), "number": None})

    async def test_worker_capability_rechecks_effective_graph_and_terminal_cleanup(
        self,
    ):
        reference, _ = await self.prepare()
        await self.admit(reference)
        capability = self.authority.issue_worker(self.job)
        self.authority.validate_job_graph(self.job, self.graph)
        authorization, _ = await self.authority.resolve_worker(
            capability,
            job_id=self.job,
            vertex_id="pr-1",
        )
        self.assertEqual(authorization.connection_id, self.connections.connection)
        with self.assertRaises(GitHubNodeAuthorizationError):
            self.authority.validate_job_graph(self.job, {"nodes": [], "edges": []})
        self.authority.finish_job(self.job)
        self.assertEqual(self.authority.jobs, {})
        self.assertEqual(self.authority.runs, {})
        with self.assertRaises(GitHubNodeAuthorizationError):
            await self.authority.resolve_worker(
                capability,
                job_id=self.job,
                vertex_id="pr-1",
            )

    async def test_recovered_job_cannot_lookup_admission_and_digest_rejects_non_json(
        self,
    ):
        with self.assertRaises(GitHubNodeAuthorizationError):
            await self.authority.resolve_worker(
                SecretStr("x" * 43),
                job_id=uuid4(),
                vertex_id="pr-1",
            )
        for graph in (
            "caller-digest",
            {"number": float("nan")},
            {"callback": self.prepare},
        ):
            with self.assertRaises(GitHubNodeAuthorizationError):
                self.authority.digest_graph(graph)
