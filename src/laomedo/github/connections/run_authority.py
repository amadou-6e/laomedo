"""Host-only one-use graph admission; connection consent never grants a write."""

import asyncio
from hmac import compare_digest
import secrets
from time import monotonic
from uuid import UUID

from pydantic import SecretStr

from laomedo.github.connections.errors import GitHubNodeAuthorizationError
from laomedo.github.connections.models import (
    GitHubNodeAdmission,
    GitHubNodeRun,
    GitHubNodeSelection,
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
        self.jobs = set()
        self.lock = asyncio.Lock()

    def _same_scope(self, left, right):
        """A second login for the same profile is a different run authority."""
        return left.owner_id == right.owner_id and compare_digest(
            left.lease_binding.get_secret_value(),
            right.lease_binding.get_secret_value(),
        )

    async def prepare(self, scope, flow_id, graph_digest, selections):
        """Verify every selection online before presenting a finite approval plan."""
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

    async def admit(self, reference, scope, *, flow_id, graph_digest, job_id, approved):
        """Consume one matching plan after confirmation; never mint mediation grants."""
        async with self.lock:
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
                or plan.graph_digest != graph_digest
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
                record = self.connections.journal.get(
                    scope.owner_id, node.selection.connection_id
                )
                if (
                    record is None
                    or record.state != "ready"
                    or record.generation != node.generation
                    or node.selection.repository not in record.repositories
                ):
                    raise GitHubNodeAuthorizationError()
            run = plan.model_copy(update={"job_id": job_id})
            self.runs[reference] = run
            self.jobs.add(job_id)
            return run

    async def resolve(self, reference, *, job_id, vertex_id, connection_id, repository):
        """Revalidate stored authority and exact selection before a node API call."""
        run = self.runs.get(reference)
        if run is None or run.job_id != job_id:
            raise GitHubNodeAuthorizationError()
        node = next(
            (node for node in run.nodes if node.selection.vertex_id == vertex_id), None
        )
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
            or authorization.generation != node.generation
            or authorization.repository != node.selection.repository
        ):
            raise GitHubNodeAuthorizationError()
        return authorization, node.selection

    def finish(self, reference):
        """Drop live account access, leaving native owner-profile history untouched."""
        run = self.runs.pop(reference, None)
        if run is not None:
            self.jobs.discard(run.job_id)
