"""Exercise the connection route through real local admission and response fences."""

from importlib.util import find_spec
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

if find_spec("langflow") is None:
    raise unittest.SkipTest("Optional Langflow runtime is not installed")

from httpx import ASGITransport, AsyncClient
from langflow.services.auth.context import (
    AuthCredentialContext,
    clear_current_auth_context,
    set_current_auth_context,
)
from starlette.applications import Starlette
from starlette.routing import Route

from laomedo.github.connections.journal import GitHubConnectionJournal
from laomedo.github.connections.service import GitHubConnectionService
from laomedo.integrations.langflow.authentication.boundary import (
    PrivateResponseBoundary,
)
from laomedo.integrations.langflow.authentication.connections import connection_index
from laomedo.integrations.langflow.authentication.policy import (
    PrivateAccessPolicy,
    PrivateGitHubResponsePolicy,
)
from laomedo.integrations.langflow.authentication.settings import PrivateBrowserSettings
from laomedo.integrations.langflow.authentication.store import PrivateSessionStore


class PrivateConnectionBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.owner = uuid4()
        self.user = SimpleNamespace(
            id=self.owner, username="synthetic", is_active=True, is_superuser=False
        )
        self.store = PrivateSessionStore(root / "leases.sqlite")
        self.issued = self.store.issue(self.owner, expires_at=time.time() + 3600)
        self.policy = PrivateAccessPolicy(
            self.store,
            PrivateBrowserSettings(origin="http://127.0.0.1:17866", runtime_root=root),
        )
        # Upstream JWT verification and runtime deployment are integration boundaries;
        # the browser lease, route, journal and response fence are real here.
        runtime = patch.object(self.policy, "verify_runtime")
        runtime.start()
        self.addCleanup(runtime.stop)
        identity = patch.object(
            self.policy, "owner_from_token", AsyncMock(return_value=self.owner)
        )
        identity.start()
        self.addCleanup(identity.stop)
        self.addCleanup(clear_current_auth_context)
        set_current_auth_context(AuthCredentialContext(method="jwt"))
        self.service = GitHubConnectionService(
            GitHubConnectionJournal(root / "connections.sqlite"),
            object(),
            callback_uri="http://127.0.0.1:17866/api/v1/laomedo/github-connections/callback",
            commit_lock=self.policy.lock,
        )

        async def index(request):
            return await connection_index(request, self.user)

        app = Starlette(routes=[Route("/api/v1/laomedo/github-connections", index)])
        app.state.private_access_policy = self.policy
        app.state.private_github_connections = self.service
        self.client = AsyncClient(
            transport=ASGITransport(
                PrivateResponseBoundary(
                    app,
                    policy=self.policy,
                    resource_policy=PrivateGitHubResponsePolicy(self.service),
                )
            ),
            base_url="http://127.0.0.1:17866",
            headers={"sec-fetch-site": "same-origin"},
            cookies={
                "access_token_lf": "synthetic-access",
                "laomedo_private_session": self.issued.cookie.get_secret_value(),
            },
        )
        self.addAsyncCleanup(self.client.aclose)

    async def test_route_requires_live_owner_lease_and_fences_response(self):
        accepted = await self.client.get("/api/v1/laomedo/github-connections")
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["index"]["connections"], [])
        self.assertEqual(accepted.headers["cache-control"], "no-store")
        self.store.revoke_browser(self.issued.cookie)
        refused = await self.client.get("/api/v1/laomedo/github-connections")
        self.assertEqual(refused.status_code, 409)
        self.assertNotIn("connections", refused.json())

    async def test_revocation_after_route_admission_blocks_response_release(self):
        original = self.service.status

        async def revoke_after_status(scope):
            result = await original(scope)
            self.store.revoke_browser(self.issued.cookie)
            return result

        with patch.object(self.service, "status", side_effect=revoke_after_status):
            response = await self.client.get("/api/v1/laomedo/github-connections")
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("connections", response.json())
