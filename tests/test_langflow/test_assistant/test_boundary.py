"""Actual ASGI origin, body and sign-out fences without provider inference."""

import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from starlette.responses import JSONResponse

from laomedo.integrations.langflow.assistant.boundary import AssistantBoundary


class EchoApplication:
    """Observe delivery only after the outer boundary has accepted a request."""

    def __init__(self, runtime):
        self.runtime = runtime
        self.bodies = []

    async def __call__(self, scope, receive, send):
        message = await receive()
        self.bodies.append(message.get("body", b""))
        if scope["path"] == "/api/v1/logout":
            self.runtime.lock_session.assert_awaited_once()
        await JSONResponse({"accepted": True})(scope, receive, send)


class BoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runtime = SimpleNamespace(ready=True, lock_session=AsyncMock())
        self.application = EchoApplication(self.runtime)
        app = AssistantBoundary(
            self.application, runtime=self.runtime, origin="http://127.0.0.1:17881"
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:17881"
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_mutation_requires_exact_origin_and_bounded_body(self):
        path = "/api/v1/laomedo/assistant/conversations"
        self.assertEqual((await self.client.post(path, json={})).status_code, 403)
        self.assertEqual(
            (
                await self.client.post(
                    path, headers={"Origin": "https://attacker.invalid"}, json={}
                )
            ).status_code,
            403,
        )
        headers = {"Origin": "http://127.0.0.1:17881"}
        self.assertEqual(
            (
                await self.client.post(path, headers=headers, content=b"x" * 65537)
            ).status_code,
            413,
        )
        self.assertEqual(self.application.bodies, [])
        self.assertEqual(
            (await self.client.post(path, headers=headers, content=b"{}")).status_code,
            200,
        )
        self.assertEqual(self.application.bodies, [b"{}"])

    async def test_logout_revokes_before_upstream_response(self):
        response = await self.client.post(
            "/api/v1/logout",
            headers={
                "Origin": "http://127.0.0.1:17881",
                "Authorization": "Bearer fixture-session",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.runtime.lock_session.assert_awaited_once_with(
            hashlib.sha256(b"fixture-session").hexdigest()
        )

    async def test_logout_remains_available_through_upstream_alias_when_revoke_fails(
        self,
    ):
        self.runtime.lock_session.side_effect = RuntimeError("database unavailable")
        response = await self.client.post(
            "/api/v1/logout",
            headers={
                "Host": "custom.localhost:17881",
                "Authorization": "Bearer fixture-session",
            },
        )
        self.assertEqual(response.status_code, 200)

    async def test_localhost_browser_origin_is_accepted_without_widening_host_trust(
        self,
    ):
        response = await self.client.post(
            "/api/v1/laomedo/assistant/conversations",
            headers={"Host": "localhost:17881", "Origin": "http://localhost:17881"},
            json={},
        )
        self.assertEqual(response.status_code, 200)

    async def test_private_mcp_has_separate_credential_gate_and_unrelated_routes_survive(
        self,
    ):
        self.assertEqual(
            (
                await self.client.post("/api/v1/laomedo/assistant/mcp/", json={})
            ).status_code,
            200,
        )
        self.assertEqual(
            (await self.client.post("/api/v1/other", json={})).status_code, 200
        )
        self.assertEqual(
            (
                await self.client.get(
                    "/api/v1/laomedo/assistant/status",
                    headers={"Host": "attacker.invalid"},
                )
            ).status_code,
            403,
        )
