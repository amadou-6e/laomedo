"""Fence outgoing browser-session authorizations before logout is processed."""

import hashlib

from starlette.requests import Request
from laomedo.integrations.langflow.provider_connections.bindings import (
    ProviderGraphBindings,
)


class ProviderSessionBoundary:
    """Invalidate pending attempts only; saved connections survive local logout."""

    def __init__(self, app, *, service):
        """Bind the local runtime's connection owner, not a global credential store."""
        self.app = app
        self.service = service

    async def __call__(self, scope, receive, send):
        """Fence the exact outgoing cookie before logout or a new profile login."""
        lease = None
        if scope["type"] == "http":
            request = Request(scope)
            cookie = request.cookies.get("access_token_lf")
            if (
                cookie
                and not request.headers.get("authorization")
                and not request.headers.get("x-api-key")
                and "x-api-key" not in request.query_params
            ):
                lease = hashlib.sha256(cookie.encode()).hexdigest()
        if (
            scope["type"] == "http"
            and scope["method"] == "POST"
            and scope["path"].rstrip("/") in {"/api/v1/logout", "/api/v1/login"}
        ):
            cookie = Request(scope).cookies.get("access_token_lf")
            if cookie:
                self.service.cancel_lease(hashlib.sha256(cookie.encode()).hexdigest())
        context = ProviderGraphBindings.session_hash.set(lease)
        try:
            await self.app(scope, receive, send)
        finally:
            ProviderGraphBindings.session_hash.reset(context)
