"""Bind native upstream profile authentication to live private browser leases."""

import asyncio
import sys
from urllib.parse import urlsplit

from pydantic import SecretStr

from laomedo.integrations.langflow.authentication.errors import (
    PrivateSessionError,
    PrivateSessionRequired,
)
from laomedo.integrations.langflow.authentication.models import PrivateBrowserContext
from laomedo.integrations.langflow.authentication.settings import (
    PRIVATE_SESSION_COOKIE_NAME,
    PrivateBrowserSettings,
)
from laomedo.integrations.langflow.authentication.store import PrivateSessionStore


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
