"""Lifecycle race/crash controls with real SQLite and synthetic external systems."""

import asyncio
from importlib.util import find_spec
from pathlib import Path
import tempfile
from urllib.parse import parse_qs, urlencode, urlsplit
import unittest
from uuid import UUID, uuid4

if find_spec("httpx2") is None or find_spec("authlib") is None:
    raise unittest.SkipTest(
        "Optional private-source protocol dependencies are not installed"
    )

from httpx2 import MockTransport, Response
from pydantic import SecretStr

from laomedo.github.connections.client import GitHubReadClient
from laomedo.github.connections.errors import (
    GitHubConnectionChanged,
    GitHubOAuthError,
    GitHubReauthorizationRequired,
    GitHubRepositoryAccessError,
    GitHubTokenUnsupported,
)
from laomedo.github.connections.journal import GitHubConnectionJournal
from laomedo.github.connections.models import GitHubConnectionScope
from laomedo.github.connections.service import GitHubConnectionService
from laomedo.github.connections.settings import GITHUB_CALLBACK_PATH
from laomedo.host.credentials.github.errors import GitHubVaultError
from test_github.test_connections.fixtures import (
    ConnectionOAuthFactory,
    ConnectionVaultFixture,
)


class GitHubConnectionServiceTests(unittest.IsolatedAsyncioTestCase):
    """No real credentials, OAuth, vault or GitHub acceptance is claimed here."""

    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.journal = GitHubConnectionJournal(
            Path(self.directory.name) / "connections.sqlite"
        )
        self.vault, self.oauth = ConnectionVaultFixture(), ConnectionOAuthFactory()
        self.now = 1000.0
        self.active = True
        self.owner = uuid4()
        self.scope = GitHubConnectionScope(
            owner_id=self.owner, lease_binding=SecretStr("lease-one"), check=self.admit
        )
        self.user = {"id": 123, "login": "synthetic"}
        self.repo = {"id": 456, "full_name": "synthetic/private", "private": True}
        self.requests = []
        self.branch_hook = None
        self.service = self.new_service()

    async def admit(self):
        """Represent a trusted request-bound upstream/lease revalidation callback."""
        if not self.active:
            raise PermissionError("synthetic session revoked")

    def provider(self, request):
        self.requests.append(request.url.path)
        data = {
            "/user": self.user,
            "/user/repos": [self.repo],
            "/user/installations": {
                "total_count": 1,
                "installations": [
                    {"id": 12, "app_slug": "synthetic-app", "suspended_at": None}
                ],
            },
            "/user/installations/12/repositories": {
                "total_count": 1,
                "repositories": [self.repo],
            },
            "/repos/synthetic/private": self.repo,
            "/repos/synthetic/private/branches": [],
        }
        if request.url.path.endswith("/branches") and self.branch_hook:
            self.branch_hook()
        return Response(200, json=data[request.url.path])

    def reader(self, credential):
        return GitHubReadClient(credential, transport=MockTransport(self.provider))

    def new_service(self):
        return GitHubConnectionService(
            self.journal,
            self.vault,
            callback_uri="http://127.0.0.1:17867" + GITHUB_CALLBACK_PATH,
            commit_lock=asyncio.Lock(),
            read_client=self.reader,
            oauth_client=self.oauth,
            clock=lambda: self.now,
        )

    async def token_attempt(self, connection_id=None):
        return await self.service.begin_token(
            self.scope, SecretStr("github_pat_synthetic"), connection_id
        )

    async def ready(self, mode="token"):
        if mode == "browser":
            await self.service.configure_app(
                self.scope,
                client_id="Iv1.synthetic",
                slug="synthetic-app",
                secret=SecretStr("synthetic-app-secret"),
            )
            attempt = await self.service.begin(self.scope)
            state = parse_qs(urlsplit(attempt["authorization_url"]).query)["state"][0]
            callback = SecretStr(
                self.service.callback_uri
                + "?"
                + urlencode({"code": "synthetic", "state": state})
            )
            attempt = await self.service.complete(self.scope, callback)
        else:
            attempt = await self.token_attempt()
        record = await self.service.confirm(
            self.scope, UUID(attempt["request_id"]), (456,)
        )
        return UUID(record["id"])

    async def test_edit_saved_token_stages_explicit_consent_without_new_login(self):
        connection_id = await self.ready()
        before = self.journal.get(self.owner, connection_id)
        attempt = await self.service.edit(self.scope, connection_id)
        self.assertEqual(attempt["phase"], "consent")
        self.assertIsNone(attempt["authorization_url"])
        self.assertEqual(attempt["inventory"]["principal"]["id"], before.principal.id)
        self.assertEqual(self.journal.get(self.owner, connection_id), before)
        await self.service.cancel(self.scope, UUID(attempt["request_id"]))
        self.assertEqual(self.journal.get(self.owner, connection_id), before)

    async def test_edit_saved_browser_preserves_app_binding_and_commits_new_generation(
        self,
    ):
        connection_id = await self.ready("browser")
        before = self.journal.get(self.owner, connection_id)
        attempt = await self.service.edit(self.scope, connection_id)
        updated = await self.service.confirm(
            self.scope, UUID(attempt["request_id"]), (456,)
        )
        self.assertEqual(updated["generation"], before.generation + 1)
        self.assertEqual(updated["app_id"], str(before.app_id))
        self.assertEqual(updated["principal"]["id"], before.principal.id)

    async def test_edit_refuses_changed_account_without_replacing_saved_access(self):
        connection_id = await self.ready()
        before = self.journal.get(self.owner, connection_id)
        self.user = {"id": 999, "login": "another-account"}
        with self.assertRaises(GitHubRepositoryAccessError):
            await self.service.edit(self.scope, connection_id)
        self.assertEqual(self.journal.get(self.owner, connection_id), before)

    async def test_candidates_are_not_read_consent_and_secrets_stay_excluded(self):
        attempt = await self.token_attempt()
        self.assertEqual(self.journal.list(self.owner), ())
        with self.assertRaises(GitHubRepositoryAccessError):
            await self.service.confirm(self.scope, UUID(attempt["request_id"]), (999,))
        connection_id = UUID(
            (
                await self.service.confirm(
                    self.scope, UUID(attempt["request_id"]), (456,)
                )
            )["id"]
        )
        before = len(self.requests)
        authorization = await self.service.authorize_read(
            self.scope, connection_id, 456
        )
        self.assertEqual(len(self.requests) - before, 3)
        self.assertTrue(self.service.current(authorization))
        status = await self.service.status(self.scope)
        self.assertNotIn("github_pat_", str(status))
        self.assertEqual(status["connections"][0]["availability"], "ready")
        with self.assertRaises(GitHubRepositoryAccessError):
            await self.service.authorize_read(self.scope, connection_id, 999)

    async def test_other_owner_or_other_browser_lease_cannot_consume_pending(self):
        attempt = await self.token_attempt()
        for owner, lease in ((uuid4(), "lease-one"), (self.owner, "lease-two")):
            other = GitHubConnectionScope(
                owner_id=owner, lease_binding=SecretStr(lease), check=self.admit
            )
            with self.assertRaises(GitHubConnectionChanged):
                await self.service.confirm(other, UUID(attempt["request_id"]), (456,))
            with self.assertRaises(GitHubConnectionChanged):
                await self.service.cancel(other, UUID(attempt["request_id"]))
        self.assertEqual(self.journal.list(self.owner), ())

    async def test_cancel_preserves_ready_and_cleans_only_provisional_custody(self):
        connection_id = await self.ready()
        old = self.journal.get(self.owner, connection_id)
        attempt = await self.token_attempt(connection_id)
        self.assertEqual(len(self.vault.values), 2)
        result = await self.service.cancel(self.scope, UUID(attempt["request_id"]))
        self.assertTrue(result["credential_cleanup_confirmed"])
        self.assertFalse(result["provider_consent_revoked"])
        self.assertEqual(self.journal.get(self.owner, connection_id), old)
        self.assertEqual(len(self.vault.values), 1)

    async def test_failed_provisional_store_retains_exact_crash_cleanup_target(self):
        self.vault.fail_store = True
        with self.assertRaises(GitHubVaultError):
            await self.token_attempt()
        self.assertEqual(self.journal.list(self.owner), ())
        self.assertEqual(len(self.vault.values), 1)
        result = await self.service.cleanup(self.scope)
        self.assertTrue(result["credential_cleanup_confirmed"])
        self.assertEqual(self.vault.values, {})

    async def test_cleanup_excludes_live_pending_secret(self):
        await self.token_attempt()
        await self.service.cleanup(self.scope)
        self.assertEqual(len(self.vault.values), 1)
        self.now += 601
        await self.service.cleanup(self.scope)
        self.assertEqual(self.vault.values, {})

    async def test_stale_reconnect_cannot_replace_newer_explicit_consent(self):
        connection_id = await self.ready()
        first, stale = await self.token_attempt(
            connection_id
        ), await self.token_attempt(connection_id)
        await self.service.confirm(self.scope, UUID(first["request_id"]), (456,))
        with self.assertRaises(GitHubConnectionChanged):
            await self.service.confirm(self.scope, UUID(stale["request_id"]), (456,))
        self.assertTrue(self.journal.current(self.owner, connection_id, 2))

    async def test_reconnect_wrong_account_keeps_previous_ready(self):
        connection_id = await self.ready()
        old = self.journal.get(self.owner, connection_id)
        self.user["id"] = 999
        with self.assertRaises(GitHubRepositoryAccessError):
            await self.token_attempt(connection_id)
        self.assertEqual(self.journal.get(self.owner, connection_id), old)

    async def test_logout_during_verification_prevents_commit(self):
        attempt = await self.token_attempt()
        self.branch_hook = lambda: setattr(self, "active", False)
        with self.assertRaises(PermissionError):
            await self.service.confirm(self.scope, UUID(attempt["request_id"]), (456,))
        self.assertEqual(self.journal.list(self.owner), ())

    async def test_disconnect_fences_before_failed_deletion_and_cleanup_retry(self):
        connection_id = await self.ready()
        authorization = await self.service.authorize_read(
            self.scope, connection_id, 456
        )
        self.vault.before_remove = lambda _: self.assertFalse(
            self.service.current(authorization)
        )
        self.vault.fail_remove = True
        result = await self.service.disconnect(self.scope, connection_id, 1)
        self.assertTrue(result["disconnected"])
        self.assertFalse(result["credential_cleanup_confirmed"])
        self.assertFalse(result["provider_consent_revoked"])
        with self.assertRaises(GitHubReauthorizationRequired):
            await self.service.authorize_read(self.scope, connection_id, 456)
        self.vault.fail_remove = False
        self.assertTrue(
            (await self.service.cleanup(self.scope))["credential_cleanup_confirmed"]
        )

    async def test_callback_consumed_once_and_wrong_lease_cannot_exchange(self):
        await self.service.configure_app(
            self.scope,
            client_id="Iv1.synthetic",
            slug="synthetic-app",
            secret=SecretStr("synthetic-app-secret"),
        )
        attempt = await self.service.begin(self.scope)
        state = parse_qs(urlsplit(attempt["authorization_url"]).query)["state"][0]
        callback = SecretStr(
            self.service.callback_uri
            + "?"
            + urlencode({"code": "synthetic", "state": state})
        )
        other = GitHubConnectionScope(
            owner_id=self.owner, lease_binding=SecretStr("different"), check=self.admit
        )
        with self.assertRaises(GitHubConnectionChanged):
            await self.service.complete(other, callback)
        self.assertEqual(self.oauth.exchanges, 0)
        await self.service.complete(self.scope, callback)
        with self.assertRaises(GitHubConnectionChanged):
            await self.service.complete(self.scope, callback)
        self.assertEqual(self.oauth.exchanges, 1)

    async def test_uncertain_refresh_stays_fenced_after_restart_and_is_not_replayed(
        self,
    ):
        connection_id = await self.ready("browser")
        self.oauth.fail_refresh = True
        with self.assertRaises(GitHubOAuthError):
            await self.service.refresh(self.scope, connection_id)
        restored = self.new_service()
        with self.assertRaises(GitHubReauthorizationRequired):
            await restored.refresh(self.scope, connection_id)
        self.assertEqual(self.oauth.refreshes, 1)
        self.assertEqual(
            self.journal.get(self.owner, connection_id).state,
            "reauthorization_required",
        )

    async def test_successful_refresh_fences_old_reads_and_preserves_consent(self):
        connection_id = await self.ready("browser")
        authorization = await self.service.authorize_read(
            self.scope, connection_id, 456
        )
        record = await self.service.refresh(self.scope, connection_id)
        self.assertEqual(record["generation"], 3)
        self.assertEqual(record["repositories"][0]["id"], 456)
        self.assertFalse(self.service.current(authorization))

    async def test_missing_ready_custody_is_not_reported_available_or_replaced(self):
        connection_id = await self.ready()
        self.vault.values.clear()
        status = await self.service.status(self.scope)
        self.assertEqual(status["connections"][0]["availability"], "unavailable")
        with self.assertRaises(GitHubReauthorizationRequired):
            await self.service.authorize_read(self.scope, connection_id, 456)

    async def test_unsupported_token_never_contacts_provider_or_vault(self):
        with self.assertRaises(GitHubTokenUnsupported):
            await self.service.begin_token(self.scope, SecretStr("ghp_classic"))
        self.assertEqual(self.requests, [])
        self.assertEqual(self.vault.values, {})
