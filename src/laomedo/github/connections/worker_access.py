"""Broker-side worker reads; no reusable credential crosses the worker boundary."""

from laomedo.github.connections.errors import GitHubNodeAuthorizationError
from laomedo.github.connections.models import GitHubConnectionScope


class GitHubWorkerReadSession:
    """Revalidate one worker capability throughout a buffered provider read."""

    def __init__(self, authority, capability, request):
        """Retain host-owned authority and one masked worker request in memory only."""
        self.authority = authority
        self.capability = capability
        self.request = request

    async def resolve(self):
        """Return exact broker-held node authority after current worker admission."""
        return await self.authority.resolve_worker(
            self.capability,
            job_id=self.request.job_id,
            vertex_id=self.request.vertex_id,
        )

    async def revalidate(self):
        """Refuse a revoked worker, ended job, lost lease or changed connection."""
        await self.authority.revalidate_worker(
            self.capability,
            job_id=self.request.job_id,
            vertex_id=self.request.vertex_id,
        )

    async def scope(self):
        """Project broker identity with a callback that also fences worker revocation."""
        authorization, selection = await self.resolve()
        run = self.authority.runs.get(self.authority.jobs.get(self.request.job_id))
        if run is None:
            raise GitHubNodeAuthorizationError()
        return (
            GitHubConnectionScope(
                owner_id=authorization.owner_id,
                lease_binding=run.scope.lease_binding,
                check=self.revalidate,
            ),
            selection,
        )


class GitHubWorkerAccess:
    """Dispatch worker reads using only the broker's admitted account and target."""

    def __init__(self, authority, reader):
        """Reuse the run authority and existing credential-custody read gateway."""
        self.authority = authority
        self.reader = reader

    async def inspect(self, capability, request):
        """Read an admitted vertex and fence revocation before returning its payload.

        The request cannot supply owner, account, repository, target or a grant.
        Provider credentials remain inside the existing broker read gateway.
        """
        session = GitHubWorkerReadSession(self.authority, capability, request)
        scope, selection = await session.scope()
        result = await self.reader.read(
            scope,
            selection.connection_id,
            kind=selection.kind,
            action="inspect",
            repository_url="https://github.com/" + selection.repository.full_name,
            labels=request.labels,
            state=request.state,
            number=selection.number,
        )
        await session.revalidate()
        return result.payload
