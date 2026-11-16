"""Fence outgoing browser-session authorizations before logout is processed."""

import hashlib

from starlette.requests import Request
from laomedo.integrations.langflow.provider_connections.bindings import (
    ProviderGraphBindings,
)
from laomedo.host.provider_connections.models import BrowserProviderSession


class ProviderSessionBoundary:
    """Invalidate pending attempts only; saved connections survive local logout."""

    def __init__(self, app, *, service):
        """Bind the local runtime's connection owner, not a global credential store."""
        self.app = app
        self.service = service

    async def __call__(self, scope, receive, send):
        """Fence the exact outgoing cookie before logout or a new profile login."""
        session = None
        if scope["type"] == "http" and scope.get("path", "").startswith("/api/"):
            request = Request(scope)
            cookie = request.cookies.get("access_token_lf")
            if (
                cookie
                and not request.headers.get("authorization")
                and not request.headers.get("x-api-key")
                and "x-api-key" not in request.query_params
            ):
                session = await self._session(cookie)
        if (
            scope["type"] == "http"
            and scope["method"] == "POST"
            and scope["path"].rstrip("/") in {"/api/v1/logout", "/api/v1/login"}
        ):
            cookie = Request(scope).cookies.get("access_token_lf")
            if cookie:
                self.service.cancel_lease(hashlib.sha256(cookie.encode()).hexdigest())
        context = ProviderGraphBindings.session.set(session)
        try:
            await self.app(scope, receive, send)
        finally:
            ProviderGraphBindings.session.reset(context)

    async def _session(self, cookie):
        """Verify the browser principal independently of the flow execution owner."""
        if ProviderGraphBindings.service is not self.service:
            return None
        from langflow.services.deps import get_auth_service, session_scope
        from langflow.services.auth.exceptions import AuthenticationError

        try:
            async with session_scope() as db:
                user = await get_auth_service()._authenticate_with_token(cookie, db)
                return BrowserProviderSession(
                    profile_id=user.id,
                    lease_hash=hashlib.sha256(cookie.encode()).hexdigest(),
                )
        except AuthenticationError:
            return None
