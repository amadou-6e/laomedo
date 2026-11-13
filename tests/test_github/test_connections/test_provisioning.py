"""Current registration fences with SQLite custody and synthetic GitHub transport."""

import asyncio
from pathlib import Path
import tempfile
from urllib.parse import parse_qs, urlencode, urlsplit
import unittest
from uuid import uuid4

from httpx2 import MockTransport, Response
from pydantic import SecretStr

from laomedo.github.connections.errors import (
    GitHubConnectionChanged,
    GitHubConnectionError,
)
from laomedo.github.connections.journal import GitHubConnectionJournal
from laomedo.github.connections.models import GitHubConnectionScope
from laomedo.github.connections.provisioning import (
    GitHubAppProvisioner,
    GitHubManifestClient,
)
from laomedo.github.connections.service import GitHubConnectionService
from laomedo.github.connections.settings import (
    GITHUB_CALLBACK_PATH,
    GITHUB_PROVISION_CALLBACK_PATH,
)
from test_github.test_connections.fixtures import ConnectionVaultFixture


class AppProvisioningTests(unittest.IsolatedAsyncioTestCase):
    """Verify one-shot registration, owner/lease admission and secret projection."""

    async def asyncSetUp(self):
        """Create isolated custody without a real account or provider acceptance."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.active = True
        self.now = 1000
        self.requests = []
        self.scope = GitHubConnectionScope(
            owner_id=uuid4(), lease_binding=SecretStr("lease-one"), check=self.admit
        )
        self.vault = ConnectionVaultFixture()
        self.service = GitHubConnectionService(
            GitHubConnectionJournal(Path(self.directory.name) / "connections.sqlite"),
            self.vault,
            callback_uri="http://127.0.0.1:17867" + GITHUB_CALLBACK_PATH,
            commit_lock=asyncio.Lock(),
        )
        self.provisioner = GitHubAppProvisioner(
            self.service,
            client_factory=lambda: GitHubManifestClient(
                transport=MockTransport(self.provider)
            ),
            clock=lambda: self.now,
        )

    async def admit(self):
        """Represent the authenticated policy's live profile and lease check."""
        if not self.active:
            raise PermissionError()

    def provider(self, request):
        """Record bounded exchange and return deliberately unrelated signing secrets."""
        self.requests.append(request)
        return Response(
            201,
            json={
                "client_id": "Iv1.synthetic",
                "client_secret": "synthetic-client-secret",
                "slug": "synthetic-local-app",
                "pem": "unused-signing-material",
                "webhook_secret": "unused-hook-material",
            },
        )

    def callback(self, manifest):
        """Construct the fixed synthetic return using the broker-created state."""
        state = parse_qs(urlsplit(manifest["action"]).query)["state"][0]
        return SecretStr(
            "http://127.0.0.1:17867"
            + GITHUB_PROVISION_CALLBACK_PATH
            + "?"
            + urlencode({"state": state, "code": "synthetic-code"})
        )

    async def test_registration_stores_only_app_secret_and_cannot_replay(self):
        manifest = await self.provisioner.begin(self.scope)
        self.assertEqual(
            manifest["manifest"]["default_permissions"],
            {"contents": "read", "metadata": "read"},
        )
        self.assertFalse(manifest["manifest"]["hook_attributes"]["active"])
        self.assertFalse(manifest["manifest"]["public"])
        result = await self.provisioner.complete(self.scope, self.callback(manifest))
        self.assertEqual(
            result, "https://github.com/apps/synthetic-local-app/installations/new"
        )
        self.assertEqual(
            [value.get_secret_value() for value in self.vault.values.values()],
            ["synthetic-client-secret"],
        )
        with self.assertRaises(GitHubConnectionChanged):
            await self.provisioner.complete(self.scope, self.callback(manifest))
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0].method, "POST")
        self.assertEqual(self.requests[0].url.host, "api.github.com")

    async def test_other_lease_and_expired_return_make_no_exchange(self):
        manifest = await self.provisioner.begin(self.scope)
        other = self.scope.model_copy(
            update={"lease_binding": SecretStr("other-lease")}
        )
        with self.assertRaises(GitHubConnectionChanged):
            await self.provisioner.complete(other, self.callback(manifest))
        self.now += 601
        with self.assertRaises(GitHubConnectionChanged):
            await self.provisioner.complete(self.scope, self.callback(manifest))
        self.assertFalse(self.requests)

    async def test_lost_exchange_is_not_replayed(self):
        manifest = await self.provisioner.begin(self.scope)
        self.provisioner.client_factory = lambda: GitHubManifestClient(
            transport=MockTransport(lambda request: Response(502))
        )
        with self.assertRaises(GitHubConnectionError):
            await self.provisioner.complete(self.scope, self.callback(manifest))
        with self.assertRaises(GitHubConnectionChanged):
            await self.provisioner.complete(self.scope, self.callback(manifest))
        self.assertFalse(self.vault.values)
