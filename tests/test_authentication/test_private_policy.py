"""Private route admission controls; upstream JWT validation is not mocked acceptance."""

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

from pydantic import ValidationError
from starlette.requests import Request
from langflow.services.auth.context import (
    AuthCredentialContext,
    clear_current_auth_context,
    set_current_auth_context,
)

from laomedo.integrations.langflow.authentication.errors import (
    PrivateSessionRequired,
    PrivateRequestRefused,
)
from laomedo.github.connections.settings import GITHUB_CALLBACK_PATH
from laomedo.integrations.langflow.authentication.policy import PrivateAccessPolicy
from laomedo.integrations.langflow.authentication.settings import PrivateBrowserSettings
from laomedo.integrations.langflow.authentication.store import PrivateSessionStore


class PrivateAccessPolicyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = PrivateSessionStore(Path(self.temp.name) / "leases.sqlite")
        self.settings = PrivateBrowserSettings(
            origin="http://127.0.0.1:17866", runtime_root=Path(self.temp.name)
        )
        self.policy = PrivateAccessPolicy(self.store, self.settings)
        runtime = patch.object(self.policy, "verify_runtime")
        runtime.start()
        self.addCleanup(runtime.stop)
        self.addCleanup(clear_current_auth_context)
        self.owner = uuid4()
        self.user = SimpleNamespace(
            id=self.owner, username="Synthetic QA", is_active=True, is_superuser=False
        )
        self.issued = self.store.issue(self.owner, expires_at=time.time() + 3600)
        set_current_auth_context(AuthCredentialContext(method="jwt"))

    def request(self, *, method="GET", origin=None, fetch_site="same-origin", extra=()):
        headers = [
            (b"host", b"127.0.0.1:17866"),
            (
                b"cookie",
                (
                    "access_token_lf=synthetic-access; laomedo_private_session="
                    + self.issued.cookie.get_secret_value()
                ).encode(),
            ),
        ]
        if origin is not None:
            headers.append((b"origin", origin.encode()))
        if fetch_site is not None:
            headers.append((b"sec-fetch-site", fetch_site.encode()))
        headers.extend(extra)
        return Request(
            {
                "type": "http",
                "method": method,
                "path": "/api/v1/laomedo/private-session",
                "scheme": "http",
                "root_path": "",
                "headers": headers,
            }
        )

    async def test_upstream_identity_and_matching_lease_are_both_required(self):
        context = await self.policy.authorize(self.request(), self.user)
        self.assertEqual(context.session.owner_id, self.owner)
        self.assertEqual(set(context.model_dump()), {"session"})
        self.assertNotIn(self.issued.cookie.get_secret_value(), repr(context))
        self.assertNotIn("synthetic-access", repr(context))
        self.store.revoke_browser(self.issued.cookie)
        with self.assertRaises(PrivateSessionRequired):
            await self.policy.authorize(self.request(), self.user)

    async def test_api_key_auto_login_external_and_missing_auth_context_are_refused(
        self,
    ):
        for method in ("api_key", "auto_login", "external", None):
            with self.subTest(method=method):
                set_current_auth_context(
                    AuthCredentialContext(method=method) if method is not None else None
                )
                with self.assertRaises(PrivateSessionRequired):
                    await self.policy.authorize(self.request(), self.user)

    async def test_different_bearer_principal_cannot_borrow_cookie_lease(self):
        self.user.id = uuid4()
        request = self.request(
            extra=((b"authorization", b"Bearer synthetic-other-user"),)
        )
        with self.assertRaises(PrivateSessionRequired):
            await self.policy.authorize(request, self.user)

    async def test_inactive_superuser_and_internal_actor_are_refused(self):
        for fields in (
            {"is_active": False},
            {"is_superuser": True},
            {"username": "__LAOMEDO_SYSTEM__"},
        ):
            user = SimpleNamespace(**(vars(self.user) | fields))
            with self.subTest(fields=fields):
                with self.assertRaises(PrivateSessionRequired):
                    await self.policy.authorize(self.request(), user)

    def test_cross_origin_missing_browser_metadata_and_duplicate_headers_are_refused(
        self,
    ):
        for request in (
            self.request(origin="http://127.0.0.1:17867"),
            self.request(fetch_site="cross-site"),
            self.request(fetch_site=None),
            self.request(method="POST"),
            self.request(extra=((b"host", b"evil.invalid"),)),
        ):
            self.assertFalse(self.policy.same_origin(request))
        self.assertTrue(
            self.policy.same_origin(
                self.request(method="POST", origin="http://127.0.0.1:17866")
            )
        )

    async def test_release_revalidates_identity_and_logout_fence(self):
        context = await self.policy.authorize(self.request(), self.user)
        with patch.object(
            self.policy, "owner_from_token", AsyncMock(return_value=self.owner)
        ):
            await self.policy.revalidate(context)
            self.store.revoke_browser(context.cookie)
            with self.assertRaises(PrivateSessionRequired):
                await self.policy.revalidate(context)

        self.issued = self.store.issue(self.owner, expires_at=time.time() + 3600)
        context = await self.policy.authorize(self.request(), self.user)
        with patch.object(
            self.policy, "owner_from_token", AsyncMock(return_value=uuid4())
        ):
            with self.assertRaises(PrivateSessionRequired):
                await self.policy.revalidate(context)

    async def test_mutations_need_exact_origin_and_current_browser_proof(self):
        context = await self.policy.authorize(self.request(), self.user)
        proof = self.policy.csrf(context).encode()
        valid = self.request(
            method="POST",
            origin=self.settings.origin,
            extra=((b"x-laomedo-csrf", proof),),
        )
        self.policy.mutation(valid, context)
        for request in (
            self.request(method="POST", origin=self.settings.origin),
            self.request(
                method="POST",
                origin=self.settings.origin,
                extra=((b"x-laomedo-csrf", b"wrong"),),
            ),
            self.request(
                method="POST",
                origin=self.settings.origin,
                extra=((b"x-laomedo-csrf", proof), (b"x-laomedo-csrf", proof)),
            ),
            self.request(
                method="POST",
                origin="https://evil.invalid",
                extra=((b"x-laomedo-csrf", proof),),
            ),
        ):
            with self.subTest(), self.assertRaises(PrivateRequestRefused):
                self.policy.mutation(request, context)

    async def test_callback_has_separate_navigation_and_live_session_admission(self):
        request = self.request(
            fetch_site="cross-site",
            extra=((b"sec-fetch-mode", b"navigate"), (b"sec-fetch-dest", b"document")),
        )
        request.scope["path"] = GITHUB_CALLBACK_PATH
        self.assertFalse(self.policy.same_origin(request))
        with patch.object(
            self.policy, "owner_from_token", AsyncMock(return_value=self.owner)
        ):
            context = await self.policy.callback(request)
            self.assertEqual(context.session.owner_id, self.owner)
            self.store.revoke_browser(context.cookie)
            with self.assertRaises(PrivateSessionRequired):
                await self.policy.callback(request)
        request.scope["headers"].append((b"host", b"evil.invalid"))
        with self.assertRaises(PrivateRequestRefused):
            await self.policy.callback(request)


class PrivateBrowserSettingsTests(unittest.TestCase):
    def test_only_an_exact_fixed_loopback_origin_is_admitted(self):
        for origin in (
            "https://127.0.0.1:17866",
            "http://localhost:17866",
            "http://127.0.0.1:17866/",
            "http://user@127.0.0.1:17866",
            "http://127.0.0.1:17866?target=other",
            "http://127.0.0.1",
        ):
            with self.subTest(origin=origin):
                with self.assertRaises(ValidationError):
                    PrivateBrowserSettings(
                        origin=origin, runtime_root=Path(tempfile.gettempdir())
                    )
