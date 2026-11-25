"""Bind native upstream profile authentication to live private browser leases."""

import asyncio
from hashlib import sha256
from hmac import compare_digest, digest
import sys
from time import monotonic, time
from urllib.parse import urlsplit

from pydantic import SecretStr

from laomedo.integrations.langflow.authentication.errors import (
    PrivateSessionError,
    PrivateSessionRequired,
    PrivateRequestRefused,
)
from laomedo.integrations.langflow.authentication.models import PrivateBrowserContext
from laomedo.integrations.langflow.authentication.settings import (
    PRIVATE_SESSION_COOKIE_NAME,
    PRIVATE_CSRF_HEADER,
    PRIVATE_CSRF_PURPOSE,
    PrivateBrowserSettings,
)
from laomedo.integrations.langflow.authentication.store import PrivateSessionStore
from laomedo.github.connections.errors import (
    GitHubConnectionChanged,
    GitHubConnectionError,
    GitHubRepositoryAccessError,
)
from laomedo.github.connections.models import (
    GitHubConnectionScope,
    GitHubResponseBinding,
)
from laomedo.github.connections.settings import (
    GITHUB_CALLBACK_PATH,
    GITHUB_PROVISION_CALLBACK_PATH,
)


class PrivateAccessPolicy:
    """Require upstream JWT identity and a live explicit-login lease together."""

    def __init__(self, store: PrivateSessionStore, settings: PrivateBrowserSettings):
        self.store = store
        self.settings = settings
        self.host = urlsplit(settings.origin).netloc
        self.lock = asyncio.Lock()

    def verify_runtime(self):
        """Refuse unsupported deployment and authentication adapters at point of use."""
        from langflow.services.deps import get_auth_service, get_settings_service
        from laomedo.integrations.langflow.local_profiles.auth import (
            LocalProfileAuthService,
        )

        service = get_settings_service()
        if service is None:
            raise PrivateSessionError()
        auth = service.auth_settings
        if (
            sys.platform != "win32"
            or auth.AUTO_LOGIN
            or auth.skip_auth_auto_login
            or auth.EXTERNAL_AUTH_ENABLED
            or auth.ENABLE_SIGNUP
            or not auth.NEW_USER_IS_ACTIVE
            or auth.API_KEY_SOURCE != "db"
            or auth.ACCESS_SAME_SITE != "lax"
            or auth.REFRESH_SAME_SITE != "lax"
            or auth.ACCESS_SECURE
            or auth.REFRESH_SECURE
            or auth.COOKIE_DOMAIN is not None
            or not isinstance(get_auth_service(), LocalProfileAuthService)
        ):
            raise PrivateSessionError()

    def same_origin(self, request) -> bool:
        """Use exact host/origin and browser metadata, without forwarded identity."""
        values = {}
        for name, value in request.scope["headers"]:
            key = name.decode("latin-1").lower()
            if key in {"host", "origin", "sec-fetch-site"} and key in values:
                return False
            values[key] = value.decode("latin-1")
        if (
            request.scope.get("root_path")
            or request.scope.get("scheme") != "http"
            or values.get("host") != self.host
            or values.get("sec-fetch-site") not in {None, "same-origin"}
        ):
            return False
        origin = values.get("origin")
        if origin is not None and origin != self.settings.origin:
            return False
        return (
            origin == self.settings.origin
            or request.method in {"GET", "HEAD"}
            and values.get("sec-fetch-site") == "same-origin"
        )

    def _ordinary_profile(self, user):
        from laomedo.integrations.langflow.local_profiles.settings import (
            SYSTEM_PROFILE_NAME,
        )

        return (
            user is not None
            and user.is_active
            and not user.is_superuser
            and user.username.casefold() != SYSTEM_PROFILE_NAME.casefold()
        )

    async def owner_from_token(self, token):
        """Validate through upstream auth; never decode or verify JWTs independently."""
        from langflow.services.auth.context import (
            AUTH_METHOD_JWT,
            get_current_auth_context,
        )
        from langflow.services.deps import get_auth_service, session_scope

        self.verify_runtime()
        try:
            async with session_scope() as db:
                user = await get_auth_service().get_current_user_from_access_token(
                    token, db
                )
                credential = get_current_auth_context()
                if (
                    credential is not None
                    and credential.method == AUTH_METHOD_JWT
                    and self._ordinary_profile(user)
                ):
                    return user.id
        except Exception:
            # Authentication diagnostics and token inputs never cross this seam.
            return None
        return None

    async def authorize(self, request, user) -> PrivateBrowserContext:
        """Bind the already upstream-authenticated principal to this browser lease."""
        from langflow.services.auth.context import (
            AUTH_METHOD_JWT,
            get_current_auth_context,
        )
        from langflow.services.auth.utils import oauth2_login

        self.verify_runtime()
        credential = get_current_auth_context()
        if (
            not self.same_origin(request)
            or credential is None
            or credential.method != AUTH_METHOD_JWT
            or not self._ordinary_profile(user)
        ):
            raise PrivateSessionRequired()
        value = request.cookies.get(PRIVATE_SESSION_COOKIE_NAME)
        token = await oauth2_login(request)
        if not value or not isinstance(token, str) or not token:
            raise PrivateSessionRequired()
        cookie = SecretStr(value)
        session = self.store.resolve(cookie, user.id)
        if session is None:
            raise PrivateSessionRequired()
        return PrivateBrowserContext(
            session=session, cookie=cookie, upstream_token=SecretStr(token)
        )

    async def revalidate(self, context: PrivateBrowserContext):
        """Repeat current upstream activity and durable lease admission before release."""
        owner = await self.owner_from_token(context.upstream_token.get_secret_value())
        if (
            owner != context.session.owner_id
            or self.store.resolve(context.cookie, context.session.owner_id) is None
        ):
            raise PrivateSessionRequired()

    def csrf(self, context: PrivateBrowserContext):
        """Derive a mutation proof held only by this admitted browser in memory."""
        return digest(
            context.cookie.get_secret_value().encode(), PRIVATE_CSRF_PURPOSE, "sha256"
        ).hex()

    def mutation(self, request, context: PrivateBrowserContext):
        """Require exact origin and one explicit proof before reading a mutation body."""
        proofs = [
            value
            for key, value in request.scope["headers"]
            if key.lower() == PRIVATE_CSRF_HEADER.encode()
        ]
        if (
            request.method != "POST"
            or not self.same_origin(request)
            or len(proofs) != 1
            or not compare_digest(proofs[0], self.csrf(context).encode())
        ):
            raise PrivateRequestRefused()

    async def callback(self, request, *, provisioning=False):
        """Admit only a fixed top-level return with upstream identity and a live lease."""
        self.verify_runtime()
        headers = {}
        for key, value in request.scope["headers"]:
            name = key.decode("latin-1").lower()
            if name in {
                "host",
                "origin",
                "sec-fetch-site",
                "sec-fetch-mode",
                "sec-fetch-dest",
            }:
                if name in headers:
                    raise PrivateRequestRefused()
                headers[name] = value.decode("latin-1")
        if (
            request.method != "GET"
            or request.scope.get("scheme") != "http"
            or request.scope.get("root_path")
            or request.scope.get("path")
            != (
                GITHUB_PROVISION_CALLBACK_PATH if provisioning else GITHUB_CALLBACK_PATH
            )
            or headers.get("host") != self.host
            or headers.get("origin") not in {None, self.settings.origin}
            or headers.get("sec-fetch-site")
            not in {"cross-site", "same-origin", "none"}
            or headers.get("sec-fetch-mode") != "navigate"
            or headers.get("sec-fetch-dest") != "document"
        ):
            raise PrivateRequestRefused()
        from langflow.services.auth.utils import oauth2_login

        try:
            token = await oauth2_login(request)
            owner = await self.owner_from_token(token)
            value = request.cookies.get(PRIVATE_SESSION_COOKIE_NAME)
            if owner is None or not isinstance(token, str) or not value:
                raise PrivateSessionRequired()
            cookie = SecretStr(value)
            session = self.store.resolve(cookie, owner)
            if session is None:
                raise PrivateSessionRequired()
            return PrivateBrowserContext(
                session=session, cookie=cookie, upstream_token=SecretStr(token)
            )
        except PrivateSessionError:
            raise
        except Exception:
            raise PrivateSessionRequired() from None


class PrivateGitHubAdmission:
    """Bind one trusted upstream context to the domain's request-local scope."""

    def __init__(self, policy: PrivateAccessPolicy, context: PrivateBrowserContext):
        """Keep raw browser credentials in the authentication adapter only."""
        self.policy, self.context = policy, context

    async def revalidate(self):
        """Repeat upstream and lease proof without accepting browser owner fields."""
        await self.policy.revalidate(self.context)

    def scope(self):
        """Project only verified owner, masked digest and host revalidation callback."""
        return GitHubConnectionScope(
            owner_id=self.context.session.owner_id,
            lease_binding=SecretStr(
                sha256(self.context.cookie.get_secret_value().encode()).hexdigest()
            ),
            check=self.revalidate,
        )


class PrivateGitHubResponsePolicy:
    """Check resource snapshots synchronously under the shared admission lock."""

    def __init__(self, service):
        """Bind the one native broker's journal and in-memory pending authority."""
        self.service = service

    def revalidate(self, binding, context: PrivateBrowserContext):
        """Refuse missing/stale resource authority before any successful body is sent."""
        if (
            not isinstance(binding, GitHubResponseBinding)
            or binding.owner_id != context.session.owner_id
        ):
            raise GitHubConnectionError()
        if binding.revision is not None:
            if self.service.journal.revision(binding.owner_id) != binding.revision:
                raise GitHubConnectionChanged()
        elif binding.connection is not None:
            expected = binding.connection
            actual = self.service.journal.get(binding.owner_id, expected.id)
            if (
                actual is None
                or actual.generation != expected.generation
                or actual.state != expected.state
            ):
                raise GitHubConnectionChanged()
        elif binding.request_id is not None:
            attempt = self.service.pending.get(binding.request_id)
            if (
                attempt is None
                or attempt.owner_id != binding.owner_id
                or attempt.expires_at <= self.service.clock()
                or not compare_digest(
                    attempt.lease_binding.get_secret_value(),
                    sha256(context.cookie.get_secret_value().encode()).hexdigest(),
                )
            ):
                raise GitHubConnectionChanged()
        else:
            authorization = binding.authorization
            if authorization.deadline <= monotonic():
                raise GitHubRepositoryAccessError()
            if not self.service.current(authorization):
                raise GitHubConnectionChanged()
