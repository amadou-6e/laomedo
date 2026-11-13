"""Real journal resource fences with synthetic session proof; no live acceptance."""

from hashlib import sha256
from pathlib import Path
import tempfile
from time import monotonic, time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from uuid import uuid4

from pydantic import SecretStr

from laomedo.github.connections.errors import (
    GitHubConnectionChanged,
    GitHubConnectionError,
    GitHubRepositoryAccessError,
)
from laomedo.github.connections.journal import GitHubConnectionJournal
from laomedo.github.connections.models import (
    GitHubConnectionAttempt,
    GitHubConnectionRecord,
    GitHubPrincipal,
    GitHubReadAuthorization,
    GitHubRepositoryIdentity,
    GitHubResponseBinding,
)
from laomedo.integrations.langflow.authentication.models import (
    PrivateBrowserContext,
    PrivateSession,
)
from laomedo.integrations.langflow.authentication.policy import (
    PrivateGitHubAdmission,
    PrivateGitHubResponsePolicy,
)


class PrivateResourcePolicyTests(unittest.IsolatedAsyncioTestCase):
    """Response checks consume exact persisted/current bindings, never browser owners."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.journal = GitHubConnectionJournal(
            Path(self.directory.name) / "connections.sqlite"
        )
        self.owner, self.connection = uuid4(), uuid4()
        self.context = PrivateBrowserContext(
            session=PrivateSession(
                owner_id=self.owner, issued_at=time(), expires_at=time() + 3600
            ),
            cookie=SecretStr("synthetic-browser-cookie"),
            upstream_token=SecretStr("synthetic-upstream-token"),
        )
        self.service = SimpleNamespace(
            journal=self.journal, pending={}, current=self.current, clock=time
        )
        self.policy = PrivateGitHubResponsePolicy(self.service)
        reference = self.journal.reserve_secret(
            self.owner, "connection", self.connection
        )
        self.record = GitHubConnectionRecord(
            id=self.connection,
            owner_id=self.owner,
            generation=1,
            mode="token",
            state="ready",
            principal=GitHubPrincipal(id=123, login="synthetic"),
            repositories=(
                GitHubRepositoryIdentity(
                    id=456, full_name="synthetic/private", private=True
                ),
            ),
            secret_reference=reference.id,
        )
        self.journal.commit_connection(self.record, expected_generation=0)

    def current(self, authorization):
        """Use the actual durable generation check; domain consent checks have service controls."""
        return self.journal.current(
            authorization.owner_id,
            authorization.connection_id,
            authorization.generation,
        )

    def authorization(self, **changes):
        """Create an admitted synthetic read snapshot with a finite real-clock deadline."""
        return GitHubReadAuthorization(
            **{
                "owner_id": self.owner,
                "connection_id": self.connection,
                "generation": 1,
                "principal": self.record.principal,
                "repository": self.record.repositories[0],
                "deadline": monotonic() + 60,
                **changes,
            }
        )

    def test_metadata_revision_refuses_late_response_after_owner_change(self):
        binding = GitHubResponseBinding(
            owner_id=self.owner, revision=self.journal.revision(self.owner)
        )
        self.policy.revalidate(binding, self.context)
        self.journal.touch(uuid4())
        self.policy.revalidate(binding, self.context)
        self.journal.touch(self.owner)
        with self.assertRaises(GitHubConnectionChanged):
            self.policy.revalidate(binding, self.context)

    def test_disconnect_fences_old_content_and_connection_result(self):
        read = GitHubResponseBinding(
            owner_id=self.owner, authorization=self.authorization()
        )
        result = GitHubResponseBinding(owner_id=self.owner, connection=self.record)
        self.policy.revalidate(read, self.context)
        self.policy.revalidate(result, self.context)
        revoked = self.journal.disconnect(self.owner, self.connection, 1)
        for binding in (read, result):
            with self.subTest(), self.assertRaises(GitHubConnectionChanged):
                self.policy.revalidate(binding, self.context)
        # A successful disconnect response describes the exact revoked result;
        # it is metadata, not continuing content authority.
        self.policy.revalidate(
            GitHubResponseBinding(owner_id=self.owner, connection=revoked), self.context
        )

    def test_expired_read_budget_refuses_even_a_current_generation(self):
        binding = GitHubResponseBinding(
            owner_id=self.owner,
            authorization=self.authorization(deadline=monotonic() - 1),
        )
        with self.assertRaises(GitHubRepositoryAccessError):
            self.policy.revalidate(binding, self.context)

    def test_pending_release_requires_same_live_browser_lease(self):
        attempt = GitHubConnectionAttempt(
            id=uuid4(),
            owner_id=self.owner,
            connection_id=self.connection,
            lease_binding=SecretStr(
                sha256(self.context.cookie.get_secret_value().encode()).hexdigest()
            ),
            mode="token",
            expected_generation=1,
            expires_at=time() + 600,
        )
        self.service.pending[attempt.id] = attempt
        binding = GitHubResponseBinding(owner_id=self.owner, request_id=attempt.id)
        self.policy.revalidate(binding, self.context)
        other = self.context.model_copy(update={"cookie": SecretStr("other-cookie")})
        with self.assertRaises(GitHubConnectionChanged):
            self.policy.revalidate(binding, other)
        self.service.pending.pop(attempt.id)
        with self.assertRaises(GitHubConnectionChanged):
            self.policy.revalidate(binding, self.context)

    def test_live_session_without_a_matching_resource_owner_is_insufficient(self):
        for binding in (None, GitHubResponseBinding(owner_id=uuid4(), revision=0)):
            with self.subTest(), self.assertRaises(GitHubConnectionError):
                self.policy.revalidate(binding, self.context)

    async def test_domain_scope_keeps_credentials_in_the_authentication_adapter(self):
        upstream = SimpleNamespace(revalidate=AsyncMock())
        scope = PrivateGitHubAdmission(upstream, self.context).scope()
        serialized = repr(scope) + scope.model_dump_json()
        self.assertNotIn("synthetic-browser-cookie", serialized)
        self.assertNotIn("synthetic-upstream-token", serialized)
        self.assertNotIn("lease_binding", scope.model_dump())
        await scope.revalidate()
        upstream.revalidate.assert_awaited_once_with(self.context)
