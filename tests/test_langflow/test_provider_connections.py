"""Browser boundary regressions; no real OAuth login or inference is performed."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi import FastAPI
from starlette.responses import JSONResponse
import time
import jwt
from fastapi.testclient import TestClient

from laomedo.agents.connections.models import LoginProgress
from laomedo.agents.connections.service import ProviderConnections
from laomedo.integrations.langflow.local_profiles.boundary import LocalProfileBoundary
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
        native_worker = patch.object(self.service.codex, "_run")
        native_worker.start()
        self.addCleanup(native_worker.stop)
        self.addCleanup(self.service.close)
        app = FastAPI()
        self.app = app

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
        with patch.object(self.service.codex, "begin") as begin:
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
        self.assertEqual(self.service.codex.attempts, {})

    def test_logged_out_cookie_cannot_read_or_manage_saved_connections(self):
        """An otherwise authenticated retained JWT cannot bypass local logout."""
        self.client.post("/api/v1/logout", headers=self.headers)
        root = "/api/v1/laomedo/provider-connections"
        identifier = str(uuid4())
        for method, path, payload in (
            ("GET", root, None),
            ("POST", root + "/attempts", {"provider": "codex"}),
            ("GET", root + "/graphs/" + identifier, None),
            ("PUT", root + "/graphs/" + identifier, {}),
            ("POST", root + "/" + identifier + "/disconnect", {}),
        ):
            with self.subTest(method=method, path=path):
                response = self.client.request(
                    method, path, json=payload, headers=self.headers
                )
                self.assertEqual(response.status_code, 401)
                self.assertEqual(
                    response.json()["detail"]["code"], "provider_session_required"
                )

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
        """Unknown integrations and unselected billing methods cannot launch login."""
        for payload in (
            {"provider": "unknown"},
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
        self.assertEqual(self.service.codex.attempts, {})

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
        )
        self.assertEqual(receipt.status_code, 401)
        self.assertEqual(
            self.service.progress(self.profile, UUID(attempt_id)).status, "cancelled"
        )

    def test_refresh_inspection_failure_preserves_the_upstream_response(self):
        """A renewal DB outage must not replace a successful upstream refresh."""
        import asyncio
        from unittest.mock import AsyncMock
        from laomedo.agents.connections.models import BrowserProviderSession

        boundary = ProviderSessionBoundary(None, service=self.service)
        session = BrowserProviderSession(profile_id=self.profile, lease_hash="original")
        message = {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"set-cookie", b"access_token_lf=fixture; HttpOnly")],
        }
        send = AsyncMock()
        with (
            patch.object(
                boundary,
                "_admit_renewal",
                new_callable=AsyncMock,
                side_effect=RuntimeError("fixture DB unavailable"),
            ),
            self.assertLogs(
                "laomedo.integrations.langflow.provider_connections.boundary",
                level="WARNING",
            ) as logs,
        ):
            asyncio.run(boundary._renew_session(session, send, message))
        send.assert_awaited_once_with(message)
        self.assertNotIn("fixture DB unavailable", " ".join(logs.output))
        self.assertEqual(self.service._lease_renewals, {})

    def test_verified_refresh_preserves_attempt_receipt_and_logout_fencing(self):
        """Mount-time JWT rotation must retain a receipt only in its original browser."""
        from laomedo.agents.connections.models import BrowserProviderSession

        key = "fixture-signing-key-that-is-at-least-32-bytes"
        original = jwt.encode(
            {"sub": str(self.profile), "exp": time.time() + 600, "jti": "original"},
            key,
            algorithm="HS256",
        )
        renewed = jwt.encode(
            {"sub": str(self.profile), "exp": time.time() + 1200, "jti": "renewed"},
            key,
            algorithm="HS256",
        )
        renewed_again = jwt.encode(
            {"sub": str(self.profile), "exp": time.time() + 1800, "jti": "again"},
            key,
            algorithm="HS256",
        )
        other = jwt.encode(
            {"sub": str(uuid4()), "exp": time.time() + 600}, key, algorithm="HS256"
        )
        response_token = renewed
        status = 200

        async def verify_cookie(boundary, cookie):
            try:
                claims = jwt.decode(cookie, key, algorithms=["HS256"])
            except jwt.InvalidTokenError:
                return None
            return BrowserProviderSession(
                profile_id=UUID(claims["sub"]),
                lease_hash=boundary.service.resolve_lease(
                    hashlib.sha256(cookie.encode()).hexdigest()
                ),
            )

        @self.app.post("/api/v1/refresh")
        async def refresh():
            response = JSONResponse({}, status_code=status)
            response.set_cookie("access_token_lf", response_token)
            return response

        self.client.cookies.clear()
        self.client.cookies.set(
            "access_token_lf", original, domain="127.0.0.1", path="/"
        )
        with patch.object(ProviderSessionBoundary, "_session", verify_cookie):
            result = self.client.post(
                "/api/v1/laomedo/provider-connections/attempts",
                json={"provider": "codex"},
                headers=self.headers,
            )
            identifier = result.json()["progress"]["attempt_id"]
            path = "/api/v1/laomedo/provider-connections/attempts/" + identifier
            self.assertEqual(
                self.client.post("/api/v1/refresh", headers=self.headers).status_code,
                200,
            )
            self.assertEqual(self.client.get(path).status_code, 200)
            self.assertEqual(
                self.service.resolve_lease(
                    hashlib.sha256(renewed.encode()).hexdigest()
                ),
                hashlib.sha256(original.encode()).hexdigest(),
            )
            response_token = other
            self.client.post("/api/v1/refresh", headers=self.headers)
            self.assertEqual(
                self.service.resolve_lease(hashlib.sha256(other.encode()).hexdigest()),
                hashlib.sha256(other.encode()).hexdigest(),
            )
            self.client.cookies.clear()
            self.client.cookies.set(
                "access_token_lf", renewed, domain="127.0.0.1", path="/"
            )
            response_token = renewed_again
            status = 401
            self.client.post("/api/v1/refresh", headers=self.headers)
            self.assertEqual(
                self.service.resolve_lease(
                    hashlib.sha256(renewed_again.encode()).hexdigest()
                ),
                hashlib.sha256(renewed_again.encode()).hexdigest(),
            )
            self.client.cookies.clear()
            self.client.cookies.set(
                "access_token_lf", renewed, domain="127.0.0.1", path="/"
            )
            self.client.post("/api/v1/logout", headers=self.headers)
            self.assertEqual(self.client.get(path).status_code, 401)
            self.client.cookies.clear()
            self.client.cookies.set(
                "access_token_lf", original, domain="127.0.0.1", path="/"
            )
            self.assertEqual(self.client.get(path).status_code, 401)

    def test_generic_attempt_routes_require_the_originating_browser_lease(self):
        """Same-profile sessions cannot observe or cancel another session's login."""
        import hashlib
        import json
        import threading
        import time
        from pydantic import SecretStr
        from laomedo.agents.agents.codex.models import CodexLoginAttempt
        from laomedo.agents.agents.claude.models import ClaudeLoginAttempt
        from laomedo.agents.connections.models import LoginProgress

        lease = hashlib.sha256(b"fixture-session").hexdigest()
        for provider in ("codex", "claude"):
            with self.subTest(provider=provider):
                attempt_id = uuid4()
                progress = LoginProgress(
                    attempt_id=attempt_id, status="connecting", provider=provider
                )
                shared = dict(
                    profile_id=self.profile,
                    lease_hash=lease,
                    candidate_id=uuid4(),
                    expires_at=time.monotonic() + 60,
                    progress=progress,
                )
                if provider == "codex":
                    item = CodexLoginAttempt(
                        **shared,
                        credential_id=uuid4(),
                        cancelled=threading.Event(),
                        ready=threading.Event(),
                        confirmation=threading.Event(),
                    )
                else:
                    item = ClaudeLoginAttempt(
                        **shared,
                        credential_id=uuid4(),
                        cancelled=threading.Event(),
                        ready=threading.Event(),
                    )
                self.service.adapter(provider).attempts[attempt_id] = item
                path = "/api/v1/laomedo/provider-connections/attempts/" + str(
                    attempt_id
                )
                self.client.cookies.set("access_token_lf", "another-session")
                self.assertEqual(self.client.get(path).status_code, 409)
                self.assertEqual(
                    self.client.post(
                        path + "/cancel", headers=self.headers
                    ).status_code,
                    409,
                )
                self.assertEqual(item.progress.status, "connecting")
                self.client.cookies.set("access_token_lf", "fixture-session")
                self.assertEqual(self.client.get(path).status_code, 200)
                response = self.client.post(path + "/cancel", headers=self.headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "cancelled")
