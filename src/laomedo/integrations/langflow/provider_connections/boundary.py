"""Fence outgoing browser-session authorizations before logout is processed."""

import hashlib
from urllib.parse import urlsplit
from uuid import UUID

from starlette.requests import Request
from laomedo.integrations.langflow.provider_connections.bindings import (
    ProviderGraphBindings,
)
from laomedo.agents.connections.models import BrowserProviderSession


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
                if session is not None and scope.get("path", "").rstrip("/") in {
                    "/api/v1/custom_component",
                    "/api/v1/custom_component/update",
                }:
                    reference = urlsplit(request.headers.get("referer", ""))
                    if (
                        reference.scheme == request.url.scheme
                        and reference.netloc == request.url.netloc
                    ):
                        parts = reference.path.rstrip("/").split("/")
                        if len(parts) == 3 and parts[1] == "flow":
                            try:
                                flow_id = UUID(parts[2])
                            except ValueError:
                                pass
                            else:
                                if await self._owns_graph(session.profile_id, flow_id):
                                    session = session.model_copy(
                                        update={"flow_id": flow_id}
                                    )
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

    async def _owns_graph(self, profile_id, flow_id):
        """Treat referrer as an untrusted hint; resolve ownership in the app database."""
        from langflow.services.database.models.flow.model import Flow
        from langflow.services.deps import session_scope
        from sqlmodel import select

        async with session_scope() as db:
            return (
                await db.exec(
                    select(Flow.id).where(
                        Flow.id == flow_id, Flow.user_id == profile_id
                    )
                )
            ).first() is not None

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
