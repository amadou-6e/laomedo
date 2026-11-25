"""Graph PR reads require a live owner-bound private account and repository."""

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock
from uuid import uuid4

from pydantic import SecretStr
from laomedo.github.connections.errors import GitHubRepositoryAccessError
from laomedo.integrations.langflow.authentication.graph_bindings import (
    PrivateGraphBindings,
)


class PrivateGraphPullRequestTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.owner, self.account = uuid4(), uuid4()
        self.policy = SimpleNamespace(revalidate=AsyncMock())
        self.context = SimpleNamespace(
            session=SimpleNamespace(owner_id=self.owner), cookie=SecretStr("test-lease")
        )
        record = SimpleNamespace(
            repositories=[SimpleNamespace(id=7, full_name="owner/repo")]
        )
        journal = SimpleNamespace(
            get=lambda owner, account: (
                record if owner == self.owner and account == self.account else None
            )
        )
        self.access = SimpleNamespace(
            connections=SimpleNamespace(journal=journal),
            read=AsyncMock(
                return_value=SimpleNamespace(payload={"pr": {"number": 12}})
            ),
        )
        self.marker = PrivateGraphBindings.admission.set(
            (self.policy, self.context, self.access)
        )

    async def asyncTearDown(self):
        PrivateGraphBindings.admission.reset(self.marker)

    async def test_reads_only_after_live_owner_authorization(self):
        result = await PrivateGraphBindings.read_pr(
            SimpleNamespace(user_id=self.owner), self.account, "OWNER/repo", 12
        )
        self.assertEqual(result["pr"]["number"], 12)
        self.policy.revalidate.assert_awaited_once_with(self.context)
        self.assertEqual(self.access.read.await_args.args[1:], (self.account, 7, 12))

    async def test_cross_owner_and_unconsented_repository_fail_closed(self):
        with self.assertRaises(GitHubRepositoryAccessError):
            await PrivateGraphBindings.read_pr(
                SimpleNamespace(user_id=uuid4()), self.account, "owner/repo", 12
            )
        with self.assertRaises(GitHubRepositoryAccessError):
            await PrivateGraphBindings.read_pr(
                SimpleNamespace(user_id=self.owner), self.account, "owner/other", 12
            )
        self.access.read.assert_not_awaited()

    async def test_revoked_lease_fails_before_account_lookup(self):
        self.policy.revalidate.side_effect = GitHubRepositoryAccessError()
        with self.assertRaises(GitHubRepositoryAccessError):
            await PrivateGraphBindings.read_pr(
                SimpleNamespace(user_id=self.owner), self.account, "owner/repo", 12
            )
        self.access.read.assert_not_awaited()
