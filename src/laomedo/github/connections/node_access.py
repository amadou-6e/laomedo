"""Compose selected-account custody with the existing Issue and PR read gateways."""

import asyncio
from concurrent.futures import TimeoutError
from time import monotonic

from laomedo.github.connections.errors import (
    GitHubNodeAuthorizationError,
    GitHubRepositoryAccessError,
)
from laomedo.github.connections.models import GitHubNodeReadResult
from laomedo.github.contract import repository_from_url, labels_value
from laomedo.github.issues.gateway import GitHubIssueGateway
from laomedo.github.pull_requests.gateway import GitHubPRGateway
from laomedo.github.transport.rest.transport import GitHubRestTransport


class GitHubNodeReadSession:
    """One finite browser read; its credential callback never runs on the loop."""

    def __init__(self, connections, scope, authorization, *, loop, clock=monotonic):
        self.connections = connections
        self.scope = scope
        self.authorization = authorization
        self.loop = loop
        self.clock = clock

    async def credential(self):
        """Revalidate online access and the exact original generation before custody."""
        original = self.authorization
        if self.clock() >= original.deadline:
            raise GitHubNodeAuthorizationError()
        current = await self.connections.authorize_read(
            self.scope, original.connection_id, original.repository.id
        )
        if (
            current.generation != original.generation
            or current.repository != original.repository
        ):
            raise GitHubNodeAuthorizationError()
        token = await self.connections.read_access_token(
            self.scope, original, lambda: self.clock() < original.deadline
        )
        if token is None:
            raise GitHubNodeAuthorizationError()
        return token

    def token(self, connection_id=None, connection_generation=None):
        """Bridge a gateway worker's token request back to the vault-owning loop."""
        original = self.authorization
        if connection_id not in (
            None,
            str(original.connection_id),
        ) or connection_generation not in (None, original.generation):
            raise GitHubNodeAuthorizationError()
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is self.loop or self.loop.is_closed():
            raise GitHubNodeAuthorizationError()
        remaining = original.deadline - self.clock()
        if remaining <= 0:
            raise GitHubNodeAuthorizationError()
        pending = asyncio.run_coroutine_threadsafe(self.credential(), self.loop)
        try:
            return pending.result(timeout=remaining)
        except TimeoutError:
            pending.cancel()
            raise GitHubNodeAuthorizationError() from None


class GitHubNodeAccess:
    """Private browser discovery/details, with no graph execution or write grant."""

    def __init__(self, connections, mediation, *, transport=GitHubRestTransport):
        self.connections = connections
        self.mediation = mediation
        self.transport = transport

    def refuse_grant(self, reference):
        """This browser-read capability cannot resolve any operation grant."""
        raise GitHubNodeAuthorizationError()

    def _read(self, session, kind, action, repository_url, labels, state, number):
        repository = repository_from_url(repository_url)
        transport = self.transport(repository, session.token)
        gateway_class = GitHubIssueGateway if kind == "issue" else GitHubPRGateway
        gateway = gateway_class(
            {repository: transport}, self.mediation, self.refuse_grant
        )
        if action == "discover":
            return gateway.discover(repository_url, labels, state)
        # Both gateways take the selected number in the fourth positional slot.
        return gateway.execute(repository_url, labels, state, number, operation=None)

    async def read(
        self,
        scope,
        connection_id,
        *,
        kind,
        action,
        repository_url,
        labels,
        state,
        number=None,
    ):
        """Read one explicitly consented repository with the existing gateway rules."""
        if (
            kind not in {"issue", "pr"}
            or action not in {"discover", "inspect"}
            or state
            not in (
                {"open", "closed", "all"}
                if kind == "issue"
                else {"open", "closed", "merged", "all"}
            )
            or (
                action == "inspect"
                and (type(number) is not int or not 0 < number <= 2**53 - 1)
            )
            or (action == "discover" and number is not None)
        ):
            raise GitHubNodeAuthorizationError()
        labels = labels_value(labels)
        repository = repository_from_url(repository_url)
        await scope.revalidate()
        selected = self.connections.selected_repository(
            scope.owner_id, connection_id, repository
        )
        if selected is None:
            raise GitHubRepositoryAccessError()
        authorization = await self.connections.authorize_read(
            scope, connection_id, selected.id
        )
        session = GitHubNodeReadSession(
            self.connections, scope, authorization, loop=asyncio.get_running_loop()
        )
        payload = await asyncio.to_thread(
            self._read, session, kind, action, repository_url, labels, state, number
        )
        if not await self.connections.confirm_read(
            scope, authorization, lambda: session.clock() < authorization.deadline
        ):
            raise GitHubNodeAuthorizationError()
        return GitHubNodeReadResult(authorization=authorization, payload=payload)
