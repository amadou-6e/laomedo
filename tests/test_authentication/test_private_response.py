"""ASGI response-release controls; no real private repository acceptance."""

import asyncio
from importlib.util import find_spec
import unittest
from unittest.mock import AsyncMock
from uuid import uuid4

if find_spec("starlette") is None or find_spec("httpx") is None:
    raise unittest.SkipTest("Optional ASGI runtime is not installed")

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from starlette.responses import Response

from laomedo.integrations.langflow.authentication.boundary import (
    PrivateResponseBoundary,
)
from laomedo.integrations.langflow.authentication.errors import (
    PrivateSessionError,
    PrivateSessionRequired,
)
from laomedo.integrations.langflow.authentication.models import (
    PrivateBrowserContext,
    PrivateSession,
)


class PrivateResponseControl:
    def __init__(self):
        self.context = PrivateBrowserContext(
            session=PrivateSession(owner_id=uuid4(), issued_at=100.0, expires_at=200.0),
            cookie=SecretStr("synthetic-private-cookie"),
            upstream_token=SecretStr("synthetic-upstream-token"),
        )
        self.status = 200
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.block = False

    async def __call__(self, scope, receive, send):
        if self.context is not None:
            scope.setdefault("state", {})["private_browser_context"] = self.context
        response = Response("synthetic-content", status_code=self.status)
        await send(
            {
                "type": "http.response.start",
                "status": self.status,
                "headers": response.raw_headers
                + [(b"cache-control", b"public, max-age=3600")],
            }
        )
        self.started.set()
        if self.block:
            await self.release.wait()
        await send({"type": "http.response.body", "body": b"synthetic-content"})


class ResponsePolicyControl:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.revalidate = AsyncMock()
        self.fence_entered = asyncio.Event()
        self.fenced = asyncio.Event()

    async def fence(self):
        self.fence_entered.set()
        async with self.lock:
            self.fenced.set()


class PrivateResponseBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.upstream = PrivateResponseControl()
        self.policy = ResponsePolicyControl()
        self.client = AsyncClient(
            transport=ASGITransport(
                PrivateResponseBoundary(self.upstream, policy=self.policy)
            ),
            base_url="http://127.0.0.1:17866",
        )
        self.addAsyncCleanup(self.client.aclose)

    async def test_missing_context_cannot_release_private_bytes(self):
        self.upstream.context = None
        response = await self.client.get("/api/v1/laomedo/private-skills/file")
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("synthetic-content", response.text)
        self.policy.revalidate.assert_not_awaited()

    async def test_logout_or_storage_failure_before_release_discards_body(self):
        for error, status in (
            (PrivateSessionRequired(), 409),
            (PrivateSessionError(), 503),
            (RuntimeError("synthetic-internal-diagnostic"), 503),
        ):
            self.policy.revalidate.side_effect = error
            with self.subTest(error=type(error).__name__):
                response = await self.client.get("/api/v1/laomedo/private-skills/file")
                self.assertEqual(response.status_code, status)
                self.assertNotIn("synthetic-content", response.text)
                self.assertNotIn("synthetic-internal-diagnostic", response.text)
                self.assertFalse(self.policy.lock.locked())

    async def test_private_success_is_no_store_and_revalidated(self):
        response = await self.client.get("/api/v1/laomedo/github-connections")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "synthetic-content")
        self.assertEqual(response.headers.get_list("cache-control"), ["no-store"])
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.policy.revalidate.assert_awaited_once_with(self.upstream.context)

    async def test_warm_cache_revalidation_cannot_bypass_admission(self):
        self.upstream.status = 304
        self.policy.revalidate.side_effect = PrivateSessionRequired()
        response = await self.client.get("/api/v1/laomedo/private-skills/file")
        self.assertEqual(response.status_code, 409)

    async def test_public_prefix_and_similar_name_are_untouched(self):
        for path in ("/api/v1/laomedo/skills", "/api/v1/laomedo/private-skills-public"):
            response = await self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "public, max-age=3600")
        self.policy.revalidate.assert_not_awaited()

    async def test_logout_fence_waits_for_already_authorized_response(self):
        self.upstream.block = True
        request = asyncio.create_task(
            self.client.get("/api/v1/laomedo/private-skills/file")
        )
        await asyncio.wait_for(self.upstream.started.wait(), timeout=5)
        fence = asyncio.create_task(self.policy.fence())
        await asyncio.wait_for(self.policy.fence_entered.wait(), timeout=5)
        self.assertFalse(self.policy.fenced.is_set())
        self.upstream.release.set()
        response, _ = await asyncio.wait_for(asyncio.gather(request, fence), timeout=5)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.policy.fenced.is_set())
