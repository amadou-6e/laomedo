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
    GitHubConnectionAttemptExpired,
    GitHubOAuthError,
    GitHubReauthorizationRequired,
    GitHubRepositoryAccessError,
    GitHubVerificationPending,
    GitHubTokenUnsupported,
)
from laomedo.github.connections.journal import GitHubConnectionJournal
from laomedo.github.connections.models import (
    GitHubConnectionScope,
    GitHubConnectionCredential,
    GitHubPrincipal,
)
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
        self.provider_status = None
        self.repository_status = None
        self.service = self.new_service()

    async def admit(self):
        """Represent a trusted request-bound upstream/lease revalidation callback."""
        if not self.active:
            raise PermissionError("synthetic session revoked")

    def provider(self, request):
        self.requests.append(request.url.path)
        if self.provider_status is not None:
            return Response(self.provider_status)
        if (
            self.repository_status is not None
            and request.url.path == "/repos/synthetic/private"
        ):
            return Response(
                self.repository_status,
                headers={"location": "https://elsewhere.invalid/repository"},
            )
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
            attempt = await self.service.begin(
                self.scope, app_id=self.journal.app(self.owner).id
            )
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

    async def test_inventory_reinspection_updates_candidates_without_consent_or_custody(
        self,
    ):
        connection_id = await self.ready("browser")
        before = self.journal.get(self.owner, connection_id)
        attempt = await self.service.edit(self.scope, connection_id)
        request_id = UUID(attempt["request_id"])
        custody = dict(self.vault.values)
        exchanges = self.oauth.exchanges
        self.repo = {"id": 789, "full_name": "synthetic/another", "private": True}
        updated = await self.service.inspect_inventory(self.scope, request_id)
        self.assertEqual(updated["mode"], "browser")
        self.assertEqual(updated["inventory"]["repositories"][0]["id"], 789)
        self.assertEqual(self.vault.values, custody)
        self.assertEqual(self.oauth.exchanges, exchanges)
        self.assertEqual(self.journal.get(self.owner, connection_id), before)
        self.assertEqual(updated["expires_at"], attempt["expires_at"])

    async def test_inventory_reinspection_rejects_principal_change_without_replacing_candidates(
        self,
    ):
        connection_id = await self.ready("browser")
        attempt = await self.service.edit(self.scope, connection_id)
        request_id = UUID(attempt["request_id"])
        before = self.service.pending[request_id]
        self.user = {"id": 999, "login": "other"}
        with self.assertRaises(GitHubRepositoryAccessError):
            await self.service.inspect_inventory(self.scope, request_id)
        self.assertEqual(self.service.pending[request_id], before)

    async def test_inventory_reinspection_fences_expiry_lease_and_saved_generation(
        self,
    ):
        connection_id = await self.ready("browser")
        attempt = await self.service.edit(self.scope, connection_id)
        request_id = UUID(attempt["request_id"])
        before = self.service.pending[request_id]
        other = self.scope.model_copy(update={"lease_binding": SecretStr("other")})
        requests = len(self.requests)
        with self.assertRaises(GitHubConnectionChanged):
            await self.service.inspect_inventory(other, request_id)
        self.assertEqual(len(self.requests), requests)
        self.now = attempt["expires_at"]
        with self.assertRaises(GitHubConnectionAttemptExpired):
            await self.service.inspect_inventory(self.scope, request_id)
        self.assertEqual(len(self.requests), requests)
        self.now = 1000.0
        record = self.journal.get(self.owner, connection_id)
        self.journal.disconnect(self.owner, connection_id, record.generation)
        with self.assertRaises(GitHubConnectionChanged):
            await self.service.inspect_inventory(self.scope, request_id)
        self.assertEqual(self.service.pending[request_id], before)

    async def test_inventory_reinspection_rejects_token_and_authorization_stages(self):
        token = await self.token_attempt()
        with self.assertRaises(GitHubConnectionChanged):
            await self.service.inspect_inventory(self.scope, UUID(token["request_id"]))
        await self.service.configure_app(
            self.scope,
            client_id="Iv1.synthetic",
            slug="synthetic-app",
            secret=SecretStr("synthetic"),
        )
        browser = await self.service.begin(
            self.scope, app_id=self.journal.app(self.owner).id
        )
        with self.assertRaises(GitHubConnectionChanged):
            await self.service.inspect_inventory(
                self.scope, UUID(browser["request_id"])
            )

    async def test_reconnect_keeps_its_private_app_after_another_account_is_configured(
        self,
    ):
        connection_id = await self.ready("browser")
        original = self.journal.get(self.owner, connection_id)
        newer = await self.service.configure_app(
            self.scope,
            client_id="Iv1.second",
            slug="second-private-app",
            secret=SecretStr("second-secret"),
            principal=GitHubPrincipal(id=999, login="second"),
        )
        attempt = await self.service.begin(self.scope, connection_id)
        pending = self.service.pending[UUID(attempt["request_id"])]
        self.assertEqual(pending.app_id, original.app_id)
        self.assertFalse(attempt["onboarding"])
        second = await self.service.begin(self.scope, app_id=UUID(newer["id"]))
        self.assertEqual(
            self.service.pending[UUID(second["request_id"])].expected_principal_id, 999
        )
        state = parse_qs(urlsplit(second["authorization_url"]).query)["state"][0]
        with self.assertRaises(GitHubRepositoryAccessError):
            await self.service.complete(
                self.scope,
                SecretStr(
                    self.service.callback_uri
                    + "?"
                    + urlencode({"code": "synthetic", "state": state})
                ),
            )
        self.assertEqual(self.journal.get(self.owner, connection_id), original)

    async def test_pending_installation_slug_remains_bound_to_original_app_version(
        self,
    ):
        connection_id = await self.ready("browser")
        attempt = await self.service.edit(self.scope, connection_id)
        request_id = UUID(attempt["request_id"])
        app_id = self.service.pending[request_id].app_id
        await self.service.configure_app(
            self.scope,
            client_id="Iv1.newer",
            slug="newer-app",
            secret=SecretStr("newer-secret"),
        )
        status = await self.service.status(self.scope)
        self.assertEqual(status["app"]["slug"], "newer-app")
        self.assertEqual(status["pending"][0]["app_slug"], "synthetic-app")
        refreshed = await self.service.inspect_inventory(self.scope, request_id)
        self.assertEqual(refreshed["inventory"]["repositories"][0]["id"], 456)
        self.assertEqual(self.service.pending[request_id].app_id, app_id)

    async def test_inventory_reinspection_refuses_inconsistent_candidate_custody(self):
        connection_id = await self.ready("browser")
        attempt = await self.service.edit(self.scope, connection_id)
        request_id = UUID(attempt["request_id"])
        pending = self.service.pending[request_id]
        token = GitHubConnectionCredential.from_token(SecretStr("github_pat_synthetic"))
        self.vault.values[pending.secret_reference] = token.to_vault_value()
        with self.assertRaises(GitHubReauthorizationRequired):
            await self.service.inspect_inventory(self.scope, request_id)
        self.assertEqual(self.service.pending[request_id], pending)

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

    async def test_add_same_account_reviews_existing_and_cancel_preserves_it(self):
        """Repeated Add is a consent review, not another saved account row."""
        connection_id = await self.ready()
        before = self.journal.get(self.owner, connection_id)
        attempt = await self.token_attempt()
        self.assertEqual(attempt["connection_id"], str(connection_id))
        await self.service.cancel(self.scope, UUID(attempt["request_id"]))
        self.assertEqual(self.journal.get(self.owner, connection_id), before)
        attempt = await self.token_attempt()
        await self.service.confirm(self.scope, UUID(attempt["request_id"]), (456,))
        self.assertEqual(len(self.journal.list(self.owner)), 1)
        self.assertTrue(self.journal.current(self.owner, connection_id, 2))
        self.assertFalse(
            (await self.service.status(self.scope))["credential_cleanup_pending"]
        )
        self.assertEqual(len(self.vault.values), 1)

    async def test_saved_replacement_survives_retired_credential_cleanup_failure(self):
        """Failed removal must stay retryable without undoing the explicit Save."""
        connection_id = await self.ready()
        attempt = await self.token_attempt()
        self.vault.fail_remove = True
        await self.service.confirm(self.scope, UUID(attempt["request_id"]), (456,))
        self.assertTrue(self.journal.current(self.owner, connection_id, 2))
        self.assertTrue(
            (await self.service.status(self.scope))["credential_cleanup_pending"]
        )
        self.vault.fail_remove = False
        await self.service.cleanup(self.scope)
        self.assertEqual(len(self.vault.values), 1)

    async def test_concurrent_new_attempts_cannot_commit_duplicate_accounts(self):
        """Two pre-consent inventories cannot evade account uniqueness at commit."""
        first, second = await self.token_attempt(), await self.token_attempt()
        await self.service.confirm(self.scope, UUID(first["request_id"]), (456,))
        with self.assertRaises(GitHubConnectionChanged):
            await self.service.confirm(self.scope, UUID(second["request_id"]), (456,))
        self.assertEqual(len(self.journal.list(self.owner)), 1)

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

    async def test_matched_expired_callback_never_exchanges_or_changes_ready_connection(
        self,
    ):
        """Delayed account selection has an actionable outcome without replay."""
        connection_id = await self.ready("browser")
        initial_exchanges = self.oauth.exchanges
        await self.service.configure_app(
            self.scope,
            client_id="Iv1.synthetic",
            slug="synthetic-app",
            secret=SecretStr("synthetic-app-secret"),
        )
        attempt = await self.service.begin(self.scope, connection_id)
        state = parse_qs(urlsplit(attempt["authorization_url"]).query)["state"][0]
        self.now += 601
        callback = SecretStr(
            self.service.callback_uri
            + "?"
            + urlencode({"code": "synthetic", "state": state})
        )
        with self.assertRaises(GitHubConnectionAttemptExpired):
            await self.service.complete(self.scope, callback)
        self.assertEqual(self.oauth.exchanges, initial_exchanges)
        self.assertTrue(self.journal.current(self.owner, connection_id, 1))

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

    async def test_disconnect_reports_own_cleanup_separately_from_abandoned_attempt(
        self,
    ):
        """A retired unrelated reservation must not imply this disconnect failed."""
        connection_id = await self.ready()
        abandoned = self.journal.reserve_secret(self.owner, "connection", uuid4())
        self.vault.store(abandoned.id, SecretStr("synthetic-abandoned"))
        result = await self.service.disconnect(self.scope, connection_id, 1)
        self.assertTrue(result["credential_cleanup_confirmed"])
        status = await self.service.status(self.scope)
        self.assertTrue(status["credential_cleanup_pending"])
        selected = next(
            item
            for item in status["connections"]
            if item["connection"]["id"] == str(connection_id)
        )
        self.assertFalse(selected["credential_cleanup_pending"])
        self.assertIsNotNone(self.vault.load(abandoned.id))

    async def test_callback_consumed_once_and_wrong_lease_cannot_exchange(self):
        await self.service.configure_app(
            self.scope,
            client_id="Iv1.synthetic",
            slug="synthetic-app",
            secret=SecretStr("synthetic-app-secret"),
        )
        attempt = await self.service.begin(
            self.scope, app_id=self.journal.app(self.owner).id
        )
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
        self.assertGreater(record["generation"], authorization.generation)
        self.assertEqual(record["repositories"][0]["id"], 456)
        self.assertFalse(self.service.current(authorization))

    async def test_rotated_credential_survives_unavailable_verification_and_restart(
        self,
    ):
        connection_id = await self.ready("browser")
        previous = self.journal.get(self.owner, connection_id)
        authorization = await self.service.authorize_read(
            self.scope, connection_id, 456
        )

        def unavailable():
            raise OSError("synthetic outage")

        self.branch_hook = unavailable
        with self.assertRaises(GitHubVerificationPending):
            await self.service.refresh(self.scope, connection_id)
        pending = self.journal.get(self.owner, connection_id)
        self.assertEqual(pending.state, "verification_pending")
        self.assertNotEqual(pending.secret_reference, previous.secret_reference)
        self.assertIsNotNone(self.vault.load(pending.secret_reference))
        await self.service.cleanup(self.scope)
        self.assertIsNotNone(self.vault.load(pending.secret_reference))
        self.assertFalse(self.service.current(authorization))
        self.assertEqual(self.oauth.refreshes, 1)
        restored = self.new_service()
        with self.assertRaises(GitHubVerificationPending):
            await restored.authorize_read(self.scope, connection_id, 456)
        with self.assertRaises(GitHubVerificationPending):
            await restored.verify(self.scope, connection_id, pending.generation)
        self.assertEqual(self.oauth.refreshes, 1)
        self.branch_hook = None
        result = await restored.verify(self.scope, connection_id, pending.generation)
        self.assertEqual(result["state"], "ready")
        self.assertEqual(self.oauth.refreshes, 1)
        await restored.authorize_read(self.scope, connection_id, 456)

    async def test_pending_verification_remains_owner_and_generation_bound_and_disconnects(
        self,
    ):
        connection_id = await self.ready("browser")
        self.branch_hook = lambda: (_ for _ in ()).throw(OSError("synthetic outage"))
        with self.assertRaises(GitHubVerificationPending):
            await self.service.refresh(self.scope, connection_id)
        pending = self.journal.get(self.owner, connection_id)
        with self.assertRaises(GitHubConnectionChanged):
            await self.service.verify(self.scope, connection_id, pending.generation - 1)
        other = GitHubConnectionScope(
            owner_id=uuid4(), lease_binding=SecretStr("other"), check=self.admit
        )
        with self.assertRaises(GitHubConnectionChanged):
            await self.service.verify(other, connection_id, pending.generation)
        await self.service.disconnect(self.scope, connection_id, pending.generation)
        self.assertIsNone(self.vault.load(pending.secret_reference))
        with self.assertRaises(GitHubConnectionChanged):
            await self.service.verify(self.scope, connection_id, pending.generation)

    async def test_pending_expired_refresh_requires_sign_in_without_an_exchange(self):
        connection_id = await self.ready("browser")
        self.branch_hook = lambda: (_ for _ in ()).throw(OSError("synthetic outage"))
        with self.assertRaises(GitHubVerificationPending):
            await self.service.refresh(self.scope, connection_id)
        pending = self.journal.get(self.owner, connection_id)
        self.now = pending.refresh_expires_at + 1
        with self.assertRaises(GitHubReauthorizationRequired):
            await self.service.verify(self.scope, connection_id, pending.generation)
        self.assertEqual(self.oauth.refreshes, 1)
        self.assertEqual(
            self.journal.get(self.owner, connection_id).state,
            "reauthorization_required",
        )

    async def test_pending_expired_access_refreshes_new_token_once(self):
        connection_id = await self.ready("browser")
        self.branch_hook = lambda: (_ for _ in ()).throw(OSError("synthetic outage"))
        with self.assertRaises(GitHubVerificationPending):
            await self.service.refresh(self.scope, connection_id)
        pending = self.journal.get(self.owner, connection_id)
        rotated = GitHubConnectionCredential.from_vault_value(
            self.vault.load(pending.secret_reference)
        )
        self.now = pending.access_expires_at + 1
        self.oauth.now = self.now
        self.branch_hook = None
        result = await self.service.verify(
            self.scope, connection_id, pending.generation
        )
        self.assertEqual(result["state"], "ready")
        self.assertEqual(self.oauth.refreshes, 2)
        self.assertEqual(
            self.oauth.refresh_tokens[1], rotated.refresh_token.get_secret_value()
        )
        self.assertNotEqual(self.oauth.refresh_tokens[0], self.oauth.refresh_tokens[1])

    async def test_confirmed_account_change_after_rotation_requires_reauthorization(
        self,
    ):
        connection_id = await self.ready("browser")
        self.user = {"id": 999, "login": "other"}
        with self.assertRaises(GitHubReauthorizationRequired):
            await self.service.refresh(self.scope, connection_id)
        self.assertEqual(
            self.journal.get(self.owner, connection_id).state,
            "reauthorization_required",
        )

    async def test_moved_repository_retires_rotated_credential_without_following_redirect(
        self,
    ):
        connection_id = await self.ready("browser")
        self.repository_status = 301
        with self.assertRaises(GitHubReauthorizationRequired):
            await self.service.refresh(self.scope, connection_id)
        record = self.journal.get(self.owner, connection_id)
        self.assertEqual(record.state, "reauthorization_required")
        self.assertIsNone(self.vault.load(record.secret_reference))
        self.assertNotIn("/repository", self.requests)

    async def test_temporary_repository_redirect_remains_retryable(self):
        connection_id = await self.ready("browser")
        self.repository_status = 307
        with self.assertRaises(GitHubVerificationPending):
            await self.service.refresh(self.scope, connection_id)
        record = self.journal.get(self.owner, connection_id)
        self.assertEqual(record.state, "verification_pending")
        self.assertIsNotNone(self.vault.load(record.secret_reference))

    async def test_missing_pending_credential_requires_sign_in(self):
        connection_id = await self.ready("browser")
        self.provider_status = 503
        with self.assertRaises(GitHubVerificationPending):
            await self.service.refresh(self.scope, connection_id)
        record = self.journal.get(self.owner, connection_id)
        self.vault.remove(record.secret_reference)
        with self.assertRaises(GitHubReauthorizationRequired):
            await self.service.verify(self.scope, connection_id, record.generation)
        self.assertEqual(
            self.journal.get(self.owner, connection_id).state,
            "reauthorization_required",
        )

    async def test_unauthenticated_rotation_requires_sign_in_but_forbidden_stays_retryable(
        self,
    ):
        for status, error, state in (
            (401, GitHubReauthorizationRequired, "reauthorization_required"),
            (403, GitHubVerificationPending, "verification_pending"),
            (404, GitHubVerificationPending, "verification_pending"),
        ):
            with self.subTest(status=status):
                self.provider_status = None
                connection_id = await self.ready("browser")
                self.provider_status = status
                with self.assertRaises(error):
                    await self.service.refresh(self.scope, connection_id)
                self.assertEqual(
                    self.journal.get(self.owner, connection_id).state, state
                )
                self.provider_status = None
                record = self.journal.get(self.owner, connection_id)
                await self.service.disconnect(
                    self.scope, connection_id, record.generation
                )

    async def test_vault_failure_after_exchange_is_fenced_and_not_replayed(self):
        connection_id = await self.ready("browser")
        self.vault.fail_store = True
        with self.assertRaises(GitHubVaultError):
            await self.service.refresh(self.scope, connection_id)
        self.assertEqual(
            self.journal.get(self.owner, connection_id).state,
            "reauthorization_required",
        )
        with self.assertRaises(GitHubReauthorizationRequired):
            await self.new_service().refresh(self.scope, connection_id)
        self.assertEqual(self.oauth.refreshes, 1)

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
