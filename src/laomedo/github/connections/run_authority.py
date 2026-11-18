"""Host-only one-use graph admission; connection consent never grants a write."""

import asyncio
from hashlib import sha256
from hmac import compare_digest
import json
import secrets
from time import monotonic
from uuid import UUID

from pydantic import SecretStr, ValidationError

from laomedo.github.connections.errors import GitHubNodeAuthorizationError
from laomedo.github.connections.models import (
    GitHubNodeAdmission,
    GitHubNodeRun,
    GitHubNodeSelection,
    GitHubWorkerLease,
)
from laomedo.github.connections.settings import (
    CONNECTION_PENDING_LIMIT,
    GITHUB_NODE_APPROVAL_SECONDS,
)


class GitHubRunAuthority:
    """Keep live owner/lease/job bindings in the vault-owning broker process."""

    def __init__(self, connections, *, clock=monotonic):
        self.connections = connections
        self.clock = clock
        self.pending = {}
        self.runs = {}
        self.jobs = {}
        self.workers = {}
        self.lock = asyncio.Lock()

    def _same_scope(self, left, right):
        """A second login for the same profile is a different run authority."""
        return left.owner_id == right.owner_id and compare_digest(
            left.lease_binding.get_secret_value(),
            right.lease_binding.get_secret_value(),
        )

    @staticmethod
    def digest_graph(graph):
        """Fingerprint the effective JSON graph, never a caller-supplied digest."""
        if not isinstance(graph, dict):
            raise GitHubNodeAuthorizationError()
        try:
            payload = json.dumps(
                graph, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeError):
            raise GitHubNodeAuthorizationError() from None
        return sha256(payload).hexdigest()

    async def prepare(self, scope, flow_id, graph, selections):
        """Verify every selection online before presenting a finite approval plan."""
        graph_digest = self.digest_graph(graph)
        selections = tuple(
            GitHubNodeSelection.model_validate(value) for value in selections
        )
        if not selections or len({item.vertex_id for item in selections}) != len(
            selections
        ):
            raise GitHubNodeAuthorizationError()
        nodes = []
        for selection in selections:
            authorization = await self.connections.authorize_read(
                scope, selection.connection_id, selection.repository.id
            )
            if authorization.repository != selection.repository:
                raise GitHubNodeAuthorizationError()
            nodes.append(
                GitHubNodeAdmission(
                    selection=selection, generation=authorization.generation
                )
            )
        # Validate the exact native identity and digest before retaining anything.
        plan = GitHubNodeRun(
            reference=SecretStr(secrets.token_urlsafe(32)),
            scope=scope,
            flow_id=flow_id,
            job_id=UUID(int=0),
            graph_digest=graph_digest,
            nodes=tuple(nodes),
        )
        async with self.lock:
            await scope.revalidate()
            self.pending = {
                key: value
                for key, value in self.pending.items()
                if value[0] > self.clock()
            }
            if len(self.pending) >= CONNECTION_PENDING_LIMIT:
                raise GitHubNodeAuthorizationError()
            reference = plan.reference.get_secret_value()
            self.pending[reference] = (
                self.clock() + GITHUB_NODE_APPROVAL_SECONDS,
                plan,
            )
        return reference, plan.nodes

    async def admit(self, reference, scope, *, flow_id, graph, job_id, approved):
        """Consume one matching plan after confirmation; never mint mediation grants."""
        async with self.lock:
            self.pending = {
                key: value
                for key, value in self.pending.items()
                if value[0] > self.clock()
            }
            entry = self.pending.get(reference)
            if entry is None:
                raise GitHubNodeAuthorizationError()
            deadline, plan = entry
            if not self._same_scope(plan.scope, scope):
                raise GitHubNodeAuthorizationError()
            # Once this owner submits, even stale/changed/denied plans cannot replay.
            del self.pending[reference]
            await scope.revalidate()
            if (
                deadline <= self.clock()
                or plan.flow_id != flow_id
                or plan.graph_digest != self.digest_graph(graph)
                or not isinstance(job_id, UUID)
                or job_id.int == 0
                or job_id in self.jobs
                or (
                    any(node.selection.operations for node in plan.nodes)
                    and approved is not True
                )
            ):
                raise GitHubNodeAuthorizationError()
            for node in plan.nodes:
                if not self.connections.run_generation_current(
                    scope.owner_id,
                    node.selection.connection_id,
                    node.generation,
                    node.selection.repository,
                ):
                    raise GitHubNodeAuthorizationError()
            run = plan.model_copy(update={"job_id": job_id, "scope": scope})
            self.runs[reference] = run
            self.jobs[job_id] = reference
            return run

    def issue_worker(self, job_id, *, deadline):
        """Issue one job-only capability for host injection into an isolated worker.

        Only an already admitted job is eligible. The clear value is returned
        once as a masked secret; the broker retains its SHA-256 digest only.
        Reissuing without explicit revocation is refused, never silently rotated.
        This internal method is not a browser or graph-callable API.
        """
        reference = self.jobs.get(job_id)
        if reference is None or reference not in self.runs or job_id in self.workers:
            raise GitHubNodeAuthorizationError()
        capability = SecretStr(secrets.token_urlsafe(32))
        try:
            lease = GitHubWorkerLease(
                digest=sha256(
                    capability.get_secret_value().encode("ascii")
                ).hexdigest(),
                expires_at=deadline,
            )
        except ValidationError:
            raise GitHubNodeAuthorizationError() from None
        if lease.expires_at <= self.clock():
            raise GitHubNodeAuthorizationError()
        run = self.runs[reference]
        if run.worker_deadline is not None and lease.expires_at > run.worker_deadline:
            raise GitHubNodeAuthorizationError()
        if run.worker_deadline is None:
            self.runs[reference] = run.model_copy(
                update={"worker_deadline": lease.expires_at}
            )
        self.workers[job_id] = lease
        return capability

    def _worker_binding(self, capability, job_id, vertex_id):
        """Authenticate one worker selector without network I/O or lock acquisition."""
        if not isinstance(capability, SecretStr):
            raise GitHubNodeAuthorizationError()
        value = capability.get_secret_value()
        if not isinstance(value, str) or len(value) != 43 or not value.isascii():
            raise GitHubNodeAuthorizationError()
        expected = self.workers.get(job_id)
        if expected is not None and expected.expires_at <= self.clock():
            self.revoke_worker(job_id)
            raise GitHubNodeAuthorizationError()
        if expected is None or not compare_digest(
            expected.digest, sha256(value.encode("ascii")).hexdigest()
        ):
            raise GitHubNodeAuthorizationError()
        run = self.run_for_job(job_id)
        node = run.node_for_vertex(vertex_id) if run is not None else None
        if node is None:
            raise GitHubNodeAuthorizationError()
        return run, node.selection

    async def revalidate_worker(self, capability, *, job_id, vertex_id):
        """Fence worker, lease and generation without reentering the commit lock.

        Credential custody invokes this while holding the connections commit
        lock. Online provider verification remains the surrounding read's job;
        this callback must not recursively invoke authorize_read or acquire that
        lock again.
        """
        run, selection = self._worker_binding(capability, job_id, vertex_id)
        await run.scope.revalidate()
        current, _ = self._worker_binding(capability, job_id, vertex_id)
        if current is not run or not self.connections.run_generation_current(
            run.scope.owner_id,
            selection.connection_id,
            run.node_for_vertex(vertex_id).generation,
            selection.repository,
        ):
            raise GitHubNodeAuthorizationError()

    async def resolve_worker(self, capability, *, job_id, vertex_id):
        """Authenticate a worker and revalidate its broker-derived selection online."""
        run, selection = self._worker_binding(capability, job_id, vertex_id)
        result = await self._resolve(
            run.reference.get_secret_value(),
            job_id=job_id,
            vertex_id=vertex_id,
            connection_id=selection.connection_id,
            repository=selection.repository.full_name,
        )
        await self.revalidate_worker(capability, job_id=job_id, vertex_id=vertex_id)
        return result

    def revoke_worker(self, job_id):
        """Stop new worker access without deleting acquired profile history."""
        self.workers.pop(job_id, None)

    def run_for_job(self, job_id):
        """Return the admitted run bound to a native job, or None."""
        return self.runs.get(self.jobs.get(job_id))

    def worker_remaining(self, job_id):
        """Return seconds left on a live worker lease, or None when none exists."""
        lease = self.workers.get(job_id)
        return None if lease is None else lease.expires_at - self.clock()

    def validate_job_graph(self, job_id, graph):
        """Refuse a changed effective worker graph before its first vertex executes."""
        run = self.runs.get(self.jobs.get(job_id))
        if run is None or run.graph_digest != self.digest_graph(graph):
            raise GitHubNodeAuthorizationError()

    async def _resolve(
        self, reference, *, job_id, vertex_id, connection_id, repository
    ):
        """Broker-internal resolution; worker callers must use resolve_worker."""
        run = self.runs.get(reference)
        if run is None or run.job_id != job_id:
            raise GitHubNodeAuthorizationError()
        node = run.node_for_vertex(vertex_id)
        if (
            node is None
            or node.selection.connection_id != connection_id
            or node.selection.repository.full_name != repository
        ):
            raise GitHubNodeAuthorizationError()
        authorization = await self.connections.authorize_read(
            run.scope, connection_id, node.selection.repository.id
        )
        if (
            self.runs.get(reference) is not run
            or not self.connections.run_generation_current(
                run.scope.owner_id,
                connection_id,
                node.generation,
                node.selection.repository,
            )
            or authorization.repository != node.selection.repository
        ):
            raise GitHubNodeAuthorizationError()
        return authorization, node.selection

    def finish(self, reference):
        """Drop live account access, leaving native owner-profile history untouched."""
        run = self.runs.pop(reference, None)
        if run is not None:
            self.revoke_worker(run.job_id)
            self.jobs.pop(run.job_id, None)

    def finish_job(self, job_id):
        """Release a terminal native job without leaking its internal reference."""
        reference = self.jobs.get(job_id)
        if reference is not None:
            self.finish(reference)
