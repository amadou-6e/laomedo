"""Fixed-endpoint Authlib exchanges; callers own pending and refresh fencing."""

import asyncio
from hmac import compare_digest
import secrets
import ssl
import time
from urllib.parse import parse_qsl, urlsplit

from authlib.integrations.httpx_client import AsyncOAuth2Client
from httpx2 import AsyncBaseTransport, AsyncHTTPTransport, Response
from pydantic import SecretStr
import truststore

from laomedo.github.connections.errors import GitHubOAuthError
from laomedo.github.connections.models import (
    GitHubConnectionCredential,
    GitHubOAuthAttempt,
)
from laomedo.github.connections.settings import (
    GITHUB_AUTHORIZE_URL,
    GITHUB_TOKEN_URL,
    OAUTH_DEADLINE_SECONDS,
    OAUTH_RESPONSE_LIMIT,
    GitHubAppSettings,
)


class GitHubOAuthTransport(AsyncBaseTransport):
    """Enforce the fixed token destination and bounded secret-bearing responses."""

    def __init__(self, transport=None):
        """Use native trust without environment proxies or any automatic retry."""
        self.transport = (
            transport
            if transport is not None
            else AsyncHTTPTransport(
                verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
                trust_env=False,
                retries=0,
            )
        )

    async def handle_async_request(self, request):
        """Deliver only the admitted POST; refuse redirects before OAuth parsing."""
        if request.method != "POST" or str(request.url) != GITHUB_TOKEN_URL:
            raise GitHubOAuthError()
        response = await self.transport.handle_async_request(request)
        try:
            if response.status_code != 200:
                raise GitHubOAuthError()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > OAUTH_RESPONSE_LIMIT:
                    raise GitHubOAuthError()
                body.extend(chunk)
            return Response(
                response.status_code,
                headers={"Content-Type": "application/json"},
                content=bytes(body),
                request=request,
            )
        finally:
            await response.aclose()

    async def aclose(self):
        """Release only this exchange's transport and pooled sockets."""
        await self.transport.aclose()


class GitHubOAuthClient:
    """Delegate protocol mechanics to Authlib without ambient credential lookup."""

    def __init__(self, settings: GitHubAppSettings, *, transport=None, clock=time.time):
        """Bind exact trusted app configuration; transport injection is host-only."""
        self.settings = settings
        self.transport = transport
        self.clock = clock

    def _client(self, **kwargs):
        """Construct a one-exchange client with no redirects, hooks or retries."""
        return AsyncOAuth2Client(
            client_id=self.settings.client_id,
            client_secret=self.settings.client_secret.get_secret_value(),
            token_endpoint_auth_method="client_secret_post",
            redirect_uri=self.settings.callback_uri,
            code_challenge_method="S256",
            scope="offline_access",
            trust_env=False,
            follow_redirects=False,
            timeout=OAUTH_DEADLINE_SECONDS,
            transport=GitHubOAuthTransport(self.transport),
            **kwargs,
        )

    async def begin(self) -> GitHubOAuthAttempt:
        """Create state and S256 PKCE without performing network I/O."""
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        async with self._client() as client:
            url, returned_state = client.create_authorization_url(
                GITHUB_AUTHORIZE_URL,
                state=state,
                code_verifier=verifier,
                allow_signup="false",
            )
        if not compare_digest(state, returned_state):
            raise GitHubOAuthError()
        return GitHubOAuthAttempt(
            state=SecretStr(state),
            verifier=SecretStr(verifier),
            authorization_url=url,
        )

    def _callback(self, url: str, attempt: GitHubOAuthAttempt) -> None:
        """Reject altered destinations, duplicate controls and state before network."""
        parsed = urlsplit(url)
        callback = urlsplit(self.settings.callback_uri)
        if (
            (parsed.scheme, parsed.netloc, parsed.path)
            != (callback.scheme, callback.netloc, callback.path)
            or parsed.fragment
            or len(url) > 16384
        ):
            raise GitHubOAuthError()
        pairs = parse_qsl(
            parsed.query, keep_blank_values=True, strict_parsing=True, max_num_fields=10
        )
        keys = [key for key, _ in pairs]
        values = dict(pairs)
        if (
            len(set(keys)) != len(keys)
            or "error" in values
            or not values.get("code")
            or len(values["code"]) > 4096
            or not values.get("state")
            or not compare_digest(
                values["state"].encode(), attempt.state.get_secret_value().encode()
            )
        ):
            raise GitHubOAuthError()

    async def complete(self, attempt: GitHubOAuthAttempt, callback_url: SecretStr):
        """Exchange once after the service consumes the owner/lease-bound attempt."""
        try:
            url = callback_url.get_secret_value()
            self._callback(url, attempt)
            async with self._client(state=attempt.state.get_secret_value()) as client:
                payload = await asyncio.wait_for(
                    client.fetch_token(
                        GITHUB_TOKEN_URL,
                        authorization_response=url,
                        code_verifier=attempt.verifier.get_secret_value(),
                        headers={"Accept": "application/json"},
                    ),
                    timeout=OAUTH_DEADLINE_SECONDS,
                )
            return GitHubConnectionCredential.from_oauth(payload, self.clock())
        except Exception:
            raise GitHubOAuthError() from None

    async def refresh(self, credential: GitHubConnectionCredential):
        """Exchange only after a durable uncertainty fence; never retry on failure."""
        try:
            if (
                credential.mode != "browser"
                or credential.refresh_token is None
                or credential.refresh_expires_at is None
                or credential.refresh_expires_at <= self.clock()
            ):
                raise GitHubOAuthError()
            async with self._client() as client:
                payload = await asyncio.wait_for(
                    client.refresh_token(
                        GITHUB_TOKEN_URL,
                        refresh_token=credential.refresh_token.get_secret_value(),
                        headers={"Accept": "application/json"},
                    ),
                    timeout=OAUTH_DEADLINE_SECONDS,
                )
            replacement = GitHubConnectionCredential.from_oauth(payload, self.clock())
            if compare_digest(
                replacement.refresh_token.get_secret_value().encode(),
                credential.refresh_token.get_secret_value().encode(),
            ):
                raise GitHubOAuthError()
            return replacement
        except Exception:
            raise GitHubOAuthError() from None
