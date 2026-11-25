"""Account-selected PR reads remain bound to their current authorization."""

import asyncio
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock
from uuid import uuid4

from laomedo.github.connections.errors import (
    GitHubConnectionChanged,
    GitHubRepositoryAccessError,
)
from laomedo.github.connections.models import GitHubReadAuthorization
from laomedo.github.connections.pull_requests.service import PrivatePullRequestAccess
from test_github.test_pull_requests.utils import raw_pr


class PrivatePullRequestTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.authorization = GitHubReadAuthorization(
            owner_id=uuid4(),
            connection_id=uuid4(),
            generation=1,
            repository={"id": 7, "full_name": "owner/repo", "private": True},
            principal={"id": 9, "login": "owner"},
            deadline=100.0,
        )
        self.scope = SimpleNamespace(revalidate=AsyncMock())
        self.client = SimpleNamespace(
            close=AsyncMock(), get_page=AsyncMock(), get=AsyncMock()
        )
        self.connections = SimpleNamespace(
            authorize_read=AsyncMock(return_value=self.authorization),
            reader=lambda authorization: self.client,
            current=lambda authorization: True,
            commit_lock=asyncio.Lock(),
        )
        self.service = PrivatePullRequestAccess(self.connections, clock=lambda: 1.0)

    async def test_discovery_preserves_filters_and_revalidates(self):
        self.client.get_page.return_value = SimpleNamespace(
            payload=[raw_pr(1, ["bug"])], next_page=False
        )
        result = await self.service.discover(
            self.scope, self.authorization.connection_id, 7
        )
        self.assertEqual(result.payload["prs"][0]["labels"], ["bug"])
        self.assertEqual(result.payload["prs"][0]["state"], "open")
        self.connections.authorize_read.assert_awaited_once_with(
            self.scope, self.authorization.connection_id, 7
        )
        self.scope.revalidate.assert_awaited_once()
        self.client.close.assert_awaited_once()

    async def test_read_refuses_after_connection_changes(self):
        self.client.get.return_value = raw_pr(1, [])
        self.connections.current = lambda authorization: False
        with self.assertRaises(GitHubConnectionChanged):
            await self.service.read(self.scope, self.authorization.connection_id, 7, 1)
        self.client.close.assert_awaited_once()

    async def test_discovery_refuses_incomplete_pagination(self):
        self.client.get_page.return_value = SimpleNamespace(payload=[], next_page=True)
        with self.assertRaises(GitHubRepositoryAccessError):
            await self.service.discover(self.scope, self.authorization.connection_id, 7)
        self.assertEqual(self.client.get_page.await_count, 10)
