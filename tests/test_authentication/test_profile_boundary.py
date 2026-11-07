"""Internal browser-boundary regressions; not real-browser acceptance."""

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from laomedo.integrations.langflow.local_profiles.boundary import LocalProfileBoundary
from laomedo.integrations.langflow.local_profiles.routes import router
from laomedo.integrations.langflow.local_profiles.models import ProfileIndex


class ProfileBrowserBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.registry = SimpleNamespace(
            list_profiles=AsyncMock(return_value=ProfileIndex()),
            create_profile=AsyncMock(),
        )
        self.app.state.local_profile_registry = self.registry
        self.app.include_router(router)
        self.app.add_middleware(LocalProfileBoundary, port=17866)
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app), base_url="http://127.0.0.1:17866"
        )
        self.addAsyncCleanup(self.client.aclose)

    async def test_picker_requires_exact_host_and_same_origin(self):
        for headers in (
            {},
            {"Origin": "http://127.0.0.1:17865"},
            {"Sec-Fetch-Site": "cross-site"},
            {"Sec-Fetch-Site": "same-origin", "Host": "evil.example:17866"},
        ):
            with self.subTest(headers=headers):
                response = await self.client.get(
                    "/api/v1/laomedo/profiles", headers=headers
                )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), {"code": "profile_request_refused"})
        self.registry.list_profiles.assert_not_awaited()
        response = await self.client.get(
            "/api/v1/laomedo/profiles", headers={"Sec-Fetch-Site": "same-origin"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"profiles": [], "pin_digits": 6})
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    async def test_registration_rejects_cross_origin_before_processing(self):
        response = await self.client.post(
            "/api/v1/laomedo/profiles",
            json={"pin": "001234"},
            headers={"Origin": "http://example.com"},
        )
        self.assertEqual(response.status_code, 403)
        self.registry.create_profile.assert_not_awaited()
        self.assertNotIn("001234", response.text)

    async def test_invalid_registration_never_echoes_body_or_validation_inputs(self):
        for payload in (
            {"name": "Work", "pin": "001234", "confirmation": "009876"},
            {
                "name": "Work",
                "pin": "001234",
                "confirmation": "001234",
                "is_superuser": True,
            },
        ):
            response = await self.client.post(
                "/api/v1/laomedo/profiles",
                json=payload,
                headers={"Origin": "http://127.0.0.1:17866"},
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json(), {"code": "profile_input_invalid"})
            self.assertNotIn("001234", response.text)
        self.registry.create_profile.assert_not_awaited()

    async def test_direct_identity_mutation_is_refused_before_upstream(self):
        for method in ("PATCH", "PUT", "DELETE"):
            response = await self.client.request(
                method,
                "/api/v1/users/any-id",
                headers={"Origin": "http://127.0.0.1:17866"},
            )
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json(), {"code": "profile_request_refused"})
