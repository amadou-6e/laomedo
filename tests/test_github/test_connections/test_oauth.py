"""Exercise actual Authlib/HTTPX protocol handling against a synthetic provider."""

import base64
import hashlib
from importlib.util import find_spec
from urllib.parse import parse_qs, urlencode, urlsplit
import unittest

if find_spec("authlib") is None or find_spec("httpx2") is None:
    raise unittest.SkipTest(
        "Optional private-source OAuth dependencies are not installed"
    )

from httpx2 import MockTransport, Response
from pydantic import SecretStr, ValidationError

from laomedo.github.connections.errors import GitHubOAuthError
from laomedo.github.connections.models import GitHubConnectionCredential
from laomedo.github.connections.oauth import GitHubOAuthClient
from laomedo.github.connections.settings import (
    GITHUB_CALLBACK_PATH,
    GITHUB_TOKEN_URL,
    OAUTH_RESPONSE_LIMIT,
    GitHubAppSettings,
)


class GitHubOAuthTests(unittest.IsolatedAsyncioTestCase):
    """Verify protocol and redaction without real credentials or GitHub effects."""

    def setUp(self):
        """Create synthetic operator input and inspect only synthetic POST bodies."""
        self.settings = GitHubAppSettings(
            client_id="Iv1.synthetic",
            slug="synthetic-app",
            client_secret=SecretStr("synthetic-app-secret"),
            callback_uri="http://127.0.0.1:17867" + GITHUB_CALLBACK_PATH,
        )
        self.requests = []
        self.payload = {
            "access_token": "synthetic-access",
            "refresh_token": "synthetic-refresh",
            "token_type": "bearer",
            "expires_in": 28800,
            "refresh_token_expires_in": 15897600,
        }
        self.status = 200
        self.raw_body = None
        self.client = GitHubOAuthClient(
            self.settings,
            transport=MockTransport(self.respond),
            clock=lambda: 1000,
        )

    def respond(self, request):
        """Record synthetic protocol requests and emit configurable provider outcomes."""
        self.requests.append(request)
        return Response(
            self.status,
            json=self.payload if self.raw_body is None else None,
            content=self.raw_body,
            headers={"Location": "https://untrusted.invalid/"},
        )

    def callback(self, attempt, **overrides):
        """Construct a synthetic browser callback without putting it in test errors."""
        query = {"code": "synthetic-code", "state": attempt.state.get_secret_value()}
        query.update(overrides)
        return SecretStr(self.settings.callback_uri + "?" + urlencode(query))

    async def test_authlib_pkce_and_fixed_exchange(self):
        """State and S256 verifier must match through the maintained OAuth library."""
        attempt = await self.client.begin()
        self.assertFalse(self.requests)
        query = parse_qs(urlsplit(attempt.authorization_url).query)
        challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(attempt.verifier.get_secret_value().encode()).digest()
            )
            .rstrip(b"=")
            .decode()
        )
        self.assertEqual(query["code_challenge"], [challenge])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["scope"], ["offline_access"])
        self.assertEqual(query["redirect_uri"], [self.settings.callback_uri])
        credential = await self.client.complete(attempt, self.callback(attempt))
        self.assertEqual(len(self.requests), 1)
        request = self.requests[0]
        self.assertEqual((request.method, str(request.url)), ("POST", GITHUB_TOKEN_URL))
        body = parse_qs(request.content.decode())
        self.assertEqual(body["code_verifier"], [attempt.verifier.get_secret_value()])
        self.assertEqual(body["client_secret"], ["synthetic-app-secret"])
        self.assertEqual(body["redirect_uri"], [self.settings.callback_uri])
        self.assertEqual(credential.access_expires_at, 29800)
        for record in (attempt, credential, self.settings):
            serialized = repr(record) + record.model_dump_json()
            self.assertNotIn("synthetic-app-secret", serialized)
            self.assertNotIn("synthetic-access", serialized)
            self.assertNotIn(attempt.state.get_secret_value(), serialized)
            self.assertNotIn(attempt.verifier.get_secret_value(), serialized)
        restored = GitHubConnectionCredential.from_vault_value(
            credential.to_vault_value()
        )
        self.assertEqual(restored.access_token, credential.access_token)

    async def test_callback_refusals_never_exchange(self):
        """Wrong state, destination, duplicates and declined consent cannot POST."""
        attempt = await self.client.begin()
        good = self.callback(attempt).get_secret_value()
        candidates = [
            self.callback(attempt, state="wrong"),
            self.callback(attempt, error="access_denied"),
            SecretStr(good + "&code=duplicate"),
            SecretStr(good + "&state=duplicate"),
            SecretStr(good + "#fragment"),
            SecretStr(good.replace("127.0.0.1", "localhost")),
            self.callback(attempt, code=""),
        ]
        for callback in candidates:
            with self.subTest():
                with self.assertRaises(GitHubOAuthError) as caught:
                    await self.client.complete(attempt, callback)
                self.assertEqual(str(caught.exception), "github_oauth_unavailable")
        self.assertFalse(self.requests)

    async def test_redirect_error_and_oversized_body_are_not_followed_or_exposed(self):
        """Transport refusal suppresses secret-bearing bodies and never retries."""
        for status, raw in (
            (302, b"synthetic-secret-error"),
            (500, b"synthetic-secret-error"),
            (200, b"x" * (OAUTH_RESPONSE_LIMIT + 1)),
            (200, b"not-json-synthetic-secret-error"),
        ):
            self.status, self.raw_body = status, raw
            attempt = await self.client.begin()
            before = len(self.requests)
            with self.assertRaises(GitHubOAuthError) as caught:
                await self.client.complete(attempt, self.callback(attempt))
            self.assertEqual(str(caught.exception), "github_oauth_unavailable")
            self.assertEqual(len(self.requests), before + 1)

    async def test_refresh_requires_rotation_and_verified_expiry(self):
        """A consumed or uncertain refresh must never be presented as ready."""
        old = GitHubConnectionCredential.from_oauth(self.payload, 1000)
        with self.assertRaises(GitHubOAuthError):
            await self.client.refresh(old)
        self.payload["refresh_token"] = "new-synthetic-refresh"
        replacement = await self.client.refresh(old)
        self.assertNotEqual(replacement.refresh_token, old.refresh_token)
        body = parse_qs(self.requests[-1].content.decode())
        self.assertEqual(body["grant_type"], ["refresh_token"])
        self.assertEqual(body["refresh_token"], ["synthetic-refresh"])
        self.payload.pop("refresh_token_expires_in")
        with self.assertRaises(GitHubOAuthError):
            await self.client.refresh(old)
        before = len(self.requests)
        static = GitHubConnectionCredential.from_token(
            SecretStr("github_pat_synthetic")
        )
        with self.assertRaises(GitHubOAuthError):
            await self.client.refresh(static)
        self.assertEqual(len(self.requests), before)

    def test_expiry_and_token_class_are_not_silently_coerced(self):
        """Malformed provider expiry or classic tokens cannot enter the ready path."""
        for lifetime in (True, "3600", 0, -1, float("inf")):
            with self.subTest(lifetime=lifetime):
                with self.assertRaises(ValueError):
                    GitHubConnectionCredential.from_oauth(
                        {**self.payload, "expires_in": lifetime},
                        1000,
                    )
        for token in ("ghp_classic", "ghu_browser", "github_pat_", "github_pat_bad\n"):
            with self.subTest():
                with self.assertRaises(ValueError):
                    GitHubConnectionCredential.from_token(SecretStr(token))

    def test_operator_callback_and_slug_cannot_choose_arbitrary_targets(self):
        """Fixed callback and installation paths reject browser-controlled URLs."""
        self.assertEqual(
            self.settings.installation_url,
            "https://github.com/apps/synthetic-app/installations/new",
        )
        payload = {
            **self.settings.model_dump(),
            "client_secret": SecretStr("synthetic"),
        }
        for callback in (
            "https://evil.invalid" + GITHUB_CALLBACK_PATH,
            "http://localhost:17867" + GITHUB_CALLBACK_PATH,
            self.settings.callback_uri + "?redirect=evil",
            self.settings.callback_uri + "/extra",
        ):
            with self.assertRaises(ValidationError):
                GitHubAppSettings(**{**payload, "callback_uri": callback})
        with self.assertRaises(ValidationError):
            GitHubAppSettings(**{**payload, "slug": "../evil"})
