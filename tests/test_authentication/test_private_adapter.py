"""ASGI controls with a synthetic upstream; not real login acceptance."""

import asyncio
from datetime import datetime, timezone
from importlib.util import find_spec
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

if find_spec("starlette") is None or find_spec("httpx") is None:
    raise unittest.SkipTest("Optional ASGI runtime is not installed")

from httpx import ASGITransport, AsyncClient
from starlette.responses import JSONResponse

from laomedo.integrations.langflow.authentication.adapter import PrivateSessionAdapter
from laomedo.integrations.langflow.authentication.errors import PrivateSessionError
from laomedo.integrations.langflow.authentication.store import PrivateSessionStore


class UpstreamPolicyControl:
    def __init__(self, owner):
        self.owner = owner
        self.lock = asyncio.Lock()
        self.validate = True

    def same_origin(self, request):
        return (
            request.headers.get("host") == "127.0.0.1:17866"
            and request.headers.get("origin") == "http://127.0.0.1:17866"
        )

    async def owner_from_token(self, token):
        return self.owner if self.validate and token == "synthetic-access" else None


class UpstreamAuthControl:
    def __init__(self):
        self.calls = []
        self.status = 200
        self.access_cookie = True
        self.refresh_cookie = True
        self.expiry = time.time() + 3600
        self.block_refresh = False
        self.refresh_entered = asyncio.Event()
        self.release_refresh = asyncio.Event()

    async def __call__(self, scope, receive, send):
        self.calls.append(scope["path"])
        if scope["path"] == "/api/v1/refresh" and self.block_refresh:
            self.refresh_entered.set()
            await self.release_refresh.wait()
        response = JSONResponse({"upstream": True}, status_code=self.status)
        if scope["path"] != "/api/v1/logout":
            if self.access_cookie:
                response.set_cookie(
                    "access_token_lf", "synthetic-access", httponly=True
                )
            if self.refresh_cookie:
                response.set_cookie(
                    "refresh_token_lf",
                    "synthetic-refresh",
                    expires=datetime.fromtimestamp(self.expiry, timezone.utc),
                    httponly=True,
                )
        await response(scope, receive, send)


class PrivateSessionAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = PrivateSessionStore(Path(self.temp.name) / "leases.sqlite")
        self.policy = UpstreamPolicyControl(uuid4())
        self.upstream = UpstreamAuthControl()
        self.app = PrivateSessionAdapter(
            self.upstream, store=self.store, policy=self.policy
        )
        self.client = AsyncClient(
            transport=ASGITransport(self.app),
            base_url="http://127.0.0.1:17866",
            headers={"Origin": "http://127.0.0.1:17866"},
        )
        self.addAsyncCleanup(self.client.aclose)

    async def login(self):
        response = await self.client.post("/api/v1/login")
        self.assertEqual(response.status_code, 200)
        value = response.cookies.get(PrivateSessionAdapter.cookie_name)
        self.assertIsNotNone(value)
        from pydantic import SecretStr

        return SecretStr(value)

    async def test_success_requires_validated_cookie_and_preserves_upstream_body(self):
        response = await self.client.post("/api/v1/login")
        self.assertEqual(response.json(), {"upstream": True})
        cookie_header = next(
            value
            for value in response.headers.get_list("set-cookie")
            if value.startswith(PrivateSessionAdapter.cookie_name + "=")
        )
        self.assertIn("HttpOnly", cookie_header)
        self.assertIn("SameSite=lax", cookie_header)
        self.assertIn("Path=/", cookie_header)
        self.assertIn("expires=", cookie_header)

    async def test_status_only_or_unverified_token_cannot_mint_private_lease(self):
        self.policy.validate = False
        response = await self.client.post("/api/v1/login")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(PrivateSessionAdapter.cookie_name, response.cookies)
        self.assertEqual(response.headers["x-laomedo-private-session"], "unavailable")
        self.policy.validate = True
        self.upstream.access_cookie = False
        response = await self.client.post("/api/v1/login")
        self.assertNotIn(PrivateSessionAdapter.cookie_name, response.cookies)

    async def test_login_error_or_missing_refresh_expiry_cannot_mint(self):
        self.upstream.status = 401
        response = await self.client.post("/api/v1/login")
        self.assertNotIn(PrivateSessionAdapter.cookie_name, response.cookies)
        self.upstream.status = 200
        self.upstream.refresh_cookie = False
        response = await self.client.post("/api/v1/login")
        self.assertNotIn(PrivateSessionAdapter.cookie_name, response.cookies)

    async def test_refresh_without_private_lease_does_not_mint_one(self):
        response = await self.client.post("/api/v1/refresh")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(PrivateSessionAdapter.cookie_name, response.cookies)
        self.assertEqual(response.headers["x-laomedo-private-session"], "unavailable")

    async def test_new_login_revokes_previous_browser_only(self):
        previous = await self.login()
        other = self.store.issue(self.policy.owner, expires_at=time.time() + 3600)
        current = await self.login()
        self.assertTrue(self.store.is_revoked(previous))
        self.assertIsNone(self.store.resolve(previous, self.policy.owner))
        self.assertIsNotNone(self.store.resolve(current, self.policy.owner))
        self.assertIsNotNone(self.store.resolve(other.cookie, self.policy.owner))

    async def test_logout_fences_without_needing_a_valid_access_token(self):
        cookie = await self.login()
        self.policy.validate = False
        response = await self.client.post("/api/v1/logout")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.store.is_revoked(cookie))
        self.assertIsNone(self.store.resolve(cookie, self.policy.owner))
        self.assertTrue(
            any(
                value.startswith(PrivateSessionAdapter.cookie_name + "=")
                and "Max-Age=0" in value
                for value in response.headers.get_list("set-cookie")
            )
        )

    async def test_known_revoked_cookie_cannot_reach_upstream_refresh(self):
        cookie = await self.login()
        self.store.revoke_browser(cookie)
        calls = len(self.upstream.calls)
        response = await self.client.post("/api/v1/refresh")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"code": "private_session_required"})
        self.assertEqual(len(self.upstream.calls), calls)
        self.assertNotIn("set-cookie", response.headers)

    async def test_revocation_failure_does_not_forward_or_claim_logout(self):
        await self.login()
        calls = len(self.upstream.calls)
        with patch.object(
            self.store, "revoke_browser", side_effect=PrivateSessionError()
        ):
            response = await self.client.post("/api/v1/logout")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"code": "app_signout_unconfirmed"})
        self.assertEqual(len(self.upstream.calls), calls)

    async def test_origin_refusal_occurs_before_upstream(self):
        response = await self.client.post(
            "/api/v1/login", headers={"Origin": "https://untrusted.invalid"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.upstream.calls, [])

    async def test_refresh_response_finishes_before_waiting_logout_fence(self):
        cookie = await self.login()
        self.upstream.block_refresh = True
        refresh = asyncio.create_task(self.client.post("/api/v1/refresh"))
        await asyncio.wait_for(self.upstream.refresh_entered.wait(), timeout=5)
        logout = asyncio.create_task(self.client.post("/api/v1/logout"))
        self.upstream.release_refresh.set()
        refreshed, logged_out = await asyncio.wait_for(
            asyncio.gather(refresh, logout), timeout=10
        )
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(logged_out.status_code, 200)
        self.assertEqual(
            self.upstream.calls[-2:], ["/api/v1/refresh", "/api/v1/logout"]
        )
        self.assertIsNone(self.store.resolve(cookie, self.policy.owner))
        self.assertTrue(self.store.is_revoked(cookie))
