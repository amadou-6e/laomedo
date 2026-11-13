"""One-time local App registration, separate from ordinary GitHub sign-in."""

import asyncio
import json
from hmac import compare_digest
import re
import secrets
import ssl
import time
from urllib.parse import parse_qsl, urlencode, urlsplit

from httpx2 import AsyncClient
from pydantic import SecretStr
import truststore

from laomedo.github.connections.errors import (
    GitHubConnectionError,
    GitHubConnectionChanged,
)
from laomedo.github.connections.models import GitHubAppProvisioningAttempt
from laomedo.github.connections.settings import (
    CONNECTION_ATTEMPT_SECONDS,
    CONNECTION_PENDING_LIMIT,
    GITHUB_API_ORIGIN,
    GITHUB_API_VERSION,
    GITHUB_MANIFEST_URL,
    GITHUB_PROVISION_CALLBACK_PATH,
    OAUTH_DEADLINE_SECONDS,
    OAUTH_RESPONSE_LIMIT,
    GitHubAppSettings,
)


class GitHubManifestClient:
    """Exchange only a validated manifest code, without ambient credentials."""

    def __init__(self, *, transport=None):
        """Allow host-owned test transport injection without changing destinations."""
        self.transport = transport

    async def convert(self, code):
        """Return App configuration from a bounded, one-shot GitHub exchange."""
        if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", code):
            raise GitHubConnectionError()
        try:
            async with asyncio.timeout(OAUTH_DEADLINE_SECONDS):
                async with AsyncClient(
                    verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
                    trust_env=False,
                    follow_redirects=False,
                    timeout=OAUTH_DEADLINE_SECONDS,
                    transport=self.transport,
                ) as client:
                    async with client.stream(
                        "POST",
                        f"{GITHUB_API_ORIGIN}/app-manifests/{code}/conversions",
                        headers={
                            "Accept": "application/vnd.github+json",
                            "X-GitHub-Api-Version": GITHUB_API_VERSION,
                        },
                    ) as response:
                        if response.status_code != 201:
                            raise GitHubConnectionError()
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(body) + len(chunk) > OAUTH_RESPONSE_LIMIT:
                                raise GitHubConnectionError()
                            body.extend(chunk)
                        value = json.loads(body)
                        if not isinstance(value, dict):
                            raise GitHubConnectionError()
                        # Deliberately drop PEM/webhook secret and all unrelated fields.
                        return {
                            key: value[key]
                            for key in ("client_id", "client_secret", "slug")
                        }
        except Exception:
            raise GitHubConnectionError() from None


class GitHubAppProvisioner:
    """Fence deployment registration by profile, live lease, state and expiry."""

    def __init__(
        self, service, *, client_factory=GitHubManifestClient, clock=time.time
    ):
        """Reuse the connection service's custody and admission commit lock."""
        self.service, self.client_factory, self.clock = service, client_factory, clock
        self.pending = {}
        self.lock = asyncio.Lock()

    async def begin(self, scope):
        """Prepare a personal, read-only App manifest after explicit operator action."""
        async with self.lock, self.service.commit_lock:
            await scope.revalidate()
            self.pending = {
                key: value
                for key, value in self.pending.items()
                if value.expires_at > self.clock()
            }
            if (
                len(self.pending) >= CONNECTION_PENDING_LIMIT
                or self.service.journal.app(scope.owner_id) is not None
            ):
                raise GitHubConnectionChanged()
            state = secrets.token_urlsafe(32)
            self.pending[state] = GitHubAppProvisioningAttempt(
                owner_id=scope.owner_id,
                lease_binding=scope.lease_binding,
                state=SecretStr(state),
                expires_at=self.clock() + CONNECTION_ATTEMPT_SECONDS,
            )
            callback = self.service.callback_uri
            origin = callback.removesuffix(
                "/api/v1/laomedo/github-connections/callback"
            )
            return {
                "action": GITHUB_MANIFEST_URL + "?" + urlencode({"state": state}),
                "manifest": {
                    "name": "Laomedo Local " + secrets.token_hex(4),
                    "url": "https://github.com/amadou-6e/laomedo",
                    "description": "Private Skill source reads for this local Laomedo deployment.",
                    "redirect_url": origin + GITHUB_PROVISION_CALLBACK_PATH,
                    "callback_urls": [callback],
                    "setup_url": origin + "/settings/github",
                    "public": False,
                    "default_events": [],
                    "hook_attributes": {
                        "url": "https://github.com/amadou-6e/laomedo",
                        "active": False,
                    },
                    "default_permissions": {"contents": "read", "metadata": "read"},
                    "request_oauth_on_install": False,
                    "setup_on_update": False,
                },
            }

    async def complete(self, scope, callback_url):
        """Consume bound registration before exchange; never replay an uncertain code."""
        parsed = urlsplit(callback_url.get_secret_value())
        expected = urlsplit(self.service.callback_uri)
        if (
            (parsed.scheme, parsed.netloc, parsed.path)
            != (expected.scheme, expected.netloc, GITHUB_PROVISION_CALLBACK_PATH)
            or parsed.fragment
            or len(callback_url.get_secret_value()) > 16384
        ):
            raise GitHubConnectionChanged()
        try:
            pairs = parse_qsl(
                parsed.query,
                keep_blank_values=True,
                strict_parsing=True,
                max_num_fields=4,
            )
            values = dict(pairs)
            if len(pairs) != 2 or set(values) != {"code", "state"}:
                raise ValueError()
        except ValueError:
            raise GitHubConnectionChanged() from None
        async with self.lock, self.service.commit_lock:
            await scope.revalidate()
            attempt = self.pending.get(values["state"])
            if (
                attempt is None
                or attempt.owner_id != scope.owner_id
                or attempt.expires_at <= self.clock()
                or not compare_digest(
                    attempt.lease_binding.get_secret_value(),
                    scope.lease_binding.get_secret_value(),
                )
            ):
                raise GitHubConnectionChanged()
            self.pending.pop(values["state"])
        app = await self.client_factory().convert(values["code"])
        settings = GitHubAppSettings(
            client_id=app["client_id"],
            slug=app["slug"],
            client_secret=SecretStr(app["client_secret"]),
            callback_uri=self.service.callback_uri,
        )
        await self.service.configure_app(
            scope,
            client_id=settings.client_id,
            slug=settings.slug,
            secret=settings.client_secret,
            require_absent=True,
        )
        return settings.installation_url
