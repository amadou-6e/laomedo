"""Browser boundary regressions; no real OAuth login or inference is performed."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from laomedo.host.provider_connections.models import LoginProgress
from laomedo.host.provider_connections.service import ProviderConnections
from laomedo.integrations.langflow.local_profiles.boundary import LocalProfileBoundary
from laomedo.integrations.langflow.local_profiles.settings import LocalProfileSettings
from laomedo.integrations.langflow.provider_connections.boundary import (
    ProviderSessionBoundary,
)
from laomedo.integrations.langflow.provider_connections.routes import (
    install_provider_routes,
)


class ProviderRouteTests(unittest.TestCase):
    """Cover origin, cookie, bounded request, native return and logout fences."""

    def setUp(self):
        """Install the actual adapter around an isolated fixture profile owner."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.profile = uuid4()
        self.service = ProviderConnections(Path(temporary.name) / "providers")
        self.addCleanup(self.service.close)
        app = FastAPI()

        async def authenticate():
            return SimpleNamespace(id=self.profile)

        install_provider_routes(
            app, self.service, authenticate, origin="http://127.0.0.1:17867"
        )
        app.add_middleware(ProviderSessionBoundary, service=self.service)
        app.add_middleware(LocalProfileBoundary, port=17867)

        @app.post("/api/v1/logout")
        async def logout():
            return {}

        self.client = TestClient(
            app, base_url="http://127.0.0.1:17867", follow_redirects=False
        )
        self.addCleanup(self.client.close)
        self.client.cookies.set("access_token_lf", "fixture-session")
        self.headers = {"Origin": "http://127.0.0.1:17867"}

    def test_read_never_launches_login_and_foreign_writes_are_refused(self):
        """Listing is inert; cross-origin pages cannot initiate authentication."""
        with patch.object(self.service, "begin") as begin:
            self.assertEqual(
                self.client.get("/api/v1/laomedo/provider-connections").json(),
                {"connections": []},
            )
            begin.assert_not_called()
        for origin in ("https://elsewhere.invalid", "null"):
            response = self.client.post(
                "/api/v1/laomedo/provider-connections/attempts",
                json={"provider": "codex"},
                headers={"Origin": origin},
            )
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.service._attempts, {})

    def test_cookie_is_mandatory_even_when_an_api_identity_exists(self):
        """An API-key/header identity cannot stand in for a browser-session lease."""
        self.client.cookies.clear()
        self.assertEqual(
            self.client.get("/api/v1/laomedo/provider-connections").status_code, 401
        )

    def test_api_key_cannot_supply_an_identity_different_from_the_cookie_lease(self):
        """Reject mixed upstream auth mechanisms instead of trusting their precedence."""
        path = "/api/v1/laomedo/provider-connections"
        self.assertEqual(
            self.client.get(path, headers={"x-api-key": "fixture-key"}).status_code, 401
        )
        self.assertEqual(
            self.client.get(path + "?x-api-key=fixture-key").status_code, 401
        )

    def test_unknown_methods_and_oversized_payloads_cannot_launch_login(self):
        """The initial adapter accepts only the explicitly selected Codex route."""
        for payload in (
            {"provider": "claude"},
            {"provider": "codex", "method": "api_key"},
        ):
            self.assertEqual(
                self.client.post(
                    "/api/v1/laomedo/provider-connections/attempts",
                    json=payload,
                    headers=self.headers,
                ).status_code,
                400,
            )
        self.assertEqual(
            self.client.post(
                "/api/v1/laomedo/provider-connections/attempts",
                content=b"x" * 1025,
                headers=self.headers,
            ).status_code,
            400,
        )
        self.assertEqual(self.service._attempts, {})

    def test_logout_invalidates_the_originating_attempt_before_return(self):
        """A late native callback cannot save a connection after local logout."""
        result = self.client.post(
            "/api/v1/laomedo/provider-connections/attempts",
            json={"provider": "codex"},
            headers=self.headers,
        )
        self.assertEqual(result.status_code, 200)
        attempt_id = result.json()["progress"]["attempt_id"]
        self.assertEqual(
            self.client.post("/api/v1/logout", headers=self.headers).status_code, 200
        )
        receipt = self.client.get(
            "/api/v1/laomedo/provider-connections/attempts/" + attempt_id
        ).json()
        self.assertEqual(receipt["status"], "cancelled")

    def test_native_return_is_bound_to_cookie_and_redirects_without_oauth_query(self):
        """Provider query data never appears in the returned Settings URL."""
        receipt = LoginProgress(
            attempt_id=uuid4(), status="connected", connection_id=uuid4()
        )
        with patch.object(self.service, "complete", return_value=receipt) as complete:
            response = self.client.get(
                "/auth/callback?code=fixture-code&state=fixture-state&client_id=oaiapp_test",
                headers={"Sec-Fetch-Site": "cross-site"},
            )
            self.assertEqual(response.status_code, 303)
            self.assertEqual(
                response.headers["location"],
                "/settings/providers?attempt=" + str(receipt.attempt_id),
            )
            self.assertEqual(response.headers["referrer-policy"], "no-referrer")
            self.assertEqual(
                complete.call_args.kwargs["lease_hash"],
                hashlib.sha256(b"fixture-session").hexdigest(),
            )

    def test_duplicate_callback_fields_are_refused_before_exchange(self):
        """Ambiguous native parameters cannot select or consume an attempt."""
        with patch.object(self.service, "complete") as complete:
            response = self.client.get("/auth/callback?state=a&state=b&code=fixture")
            self.assertEqual(
                response.headers["location"], "/settings/providers?login=failed"
            )
            complete.assert_not_called()


class ProfileBrowserOriginTests(unittest.TestCase):
    """A preview alias changes only its exact browser boundary, never the bind."""

    async def login(self):
        return {"boundary": "accepted"}

    def test_named_loopback_origin_accepts_only_the_selected_host_and_origin(self):
        app = FastAPI()
        app.add_middleware(
            LocalProfileBoundary, port=17884, browser_host="provider-284.localhost"
        )

        app.add_api_route("/api/v1/login", self.login, methods=["POST"])

        with TestClient(app, base_url="http://provider-284.localhost:17884") as client:
            for origin, host, expected in (
                (
                    "http://provider-284.localhost:17884",
                    "provider-284.localhost:17884",
                    200,
                ),
                ("http://127.0.0.1:17884", "provider-284.localhost:17884", 403),
                (
                    "http://provider-284.localhost:55753",
                    "provider-284.localhost:17884",
                    403,
                ),
                ("http://provider-284.localhost:17884", "127.0.0.1:17884", 403),
            ):
                with self.subTest(origin=origin, host=host):
                    self.assertEqual(
                        client.post(
                            "/api/v1/login", headers={"Origin": origin, "Host": host}
                        ).status_code,
                        expected,
                    )

    def test_browser_hostname_settings_refuse_non_loopback_or_ambiguous_hosts(self):
        for host in (
            "example.com",
            "localhost.example.com",
            "127.0.0.2",
            "a.b.localhost",
            "provider.localhost:17884",
            "*.localhost",
            "provider.localhost\n",
        ):
            with self.subTest(host=host), self.assertRaises(ValidationError):
                LocalProfileSettings(
                    LAOMEDO_LOCAL_PROFILE_RUNTIME=".",
                    LAOMEDO_LOCAL_PROFILE_BROWSER_HOST=host,
                )
        for host in ("127.0.0.1", "provider-284.localhost"):
            settings = LocalProfileSettings(
                LAOMEDO_LOCAL_PROFILE_RUNTIME=".",
                LAOMEDO_LOCAL_PROFILE_BROWSER_HOST=host,
            )
            self.assertEqual(settings.browser_host, host)
