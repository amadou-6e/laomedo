"""Observe upstream login cookies and durably fence private browser logout."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie

from pydantic import SecretStr
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from laomedo.integrations.langflow.authentication.errors import PrivateSessionError
from laomedo.integrations.langflow.authentication.settings import (
    PRIVATE_SESSION_COOKIE_NAME,
)


class PrivateSessionAdapter:
    """Supplement upstream auth without consuming credentials or minting JWTs.

    The trusted policy supplies a shared process-local lock, exact origin checks
    and upstream access-cookie validation. A failed private lease operation never
    converts a successful upstream login into a claim of private access.
    """

    cookie_name = PRIVATE_SESSION_COOKIE_NAME

    def __init__(self, app, *, store, policy):
        self.app = app
        self.store = store
        self.policy = policy

    async def __call__(self, scope, receive, send):
        path = scope.get("path")
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or path not in {"/api/v1/login", "/api/v1/refresh", "/api/v1/logout"}
        ):
            return await self.app(scope, receive, send)
        request = Request(scope)
        if scope.get("root_path") or not self.policy.same_origin(request):
            return await self._refuse(
                scope, receive, send, 403, "profile_request_refused"
            )
        incoming = request.cookies.get(self.cookie_name)
        cookie = SecretStr(incoming) if incoming else None
        # Holding the lock until the upstream response finishes prevents a
        # delayed response-start from passing a completed logout fence.
        async with self.policy.lock:
            try:
                if path == "/api/v1/logout" and cookie is not None:
                    self.store.revoke_browser(cookie)
                if (
                    path == "/api/v1/refresh"
                    and cookie is not None
                    and self.store.is_revoked(cookie)
                ):
                    return await self._refuse(
                        scope, receive, send, 409, "private_session_required"
                    )
            except PrivateSessionError:
                return await self._refuse(
                    scope,
                    receive,
                    send,
                    503,
                    (
                        "app_signout_unconfirmed"
                        if path == "/api/v1/logout"
                        else "private_session_unavailable"
                    ),
                )

            async def observe(message):
                if message["type"] != "http.response.start":
                    return await send(message)
                message = {**message, "headers": list(message.get("headers", []))}
                if path == "/api/v1/logout" and 200 <= message["status"] < 300:
                    message["headers"].extend(self._cookie_headers(None))
                elif message["status"] == 200 and path != "/api/v1/logout":
                    try:
                        outgoing = SimpleCookie()
                        names = []
                        for name, value in message["headers"]:
                            if name.lower() == b"set-cookie":
                                part = SimpleCookie()
                                part.load(value.decode("latin-1"))
                                names.extend(part.keys())
                                outgoing.update(part)
                        if names.count("access_token_lf") != 1:
                            raise PrivateSessionError()
                        owner = await self.policy.owner_from_token(
                            outgoing["access_token_lf"].value
                        )
                        expiry = self._refresh_expiry(outgoing, names)
                        if owner is None:
                            raise PrivateSessionError()
                        if path == "/api/v1/login":
                            if cookie is not None:
                                self.store.revoke_browser(cookie)
                            issued = self.store.issue(owner, expires_at=expiry)
                            message["headers"].extend(
                                self._cookie_headers(issued.cookie, expiry)
                            )
                        elif cookie is None or not self.store.renew(
                            cookie, owner, expires_at=expiry
                        ):
                            raise PrivateSessionError()
                        else:
                            message["headers"].extend(
                                self._cookie_headers(cookie, expiry)
                            )
                    except Exception:
                        # Upstream login remains upstream-owned; the private
                        # dependency separately refuses an unavailable lease.
                        message["headers"].append(
                            (b"x-laomedo-private-session", b"unavailable")
                        )
                await send(message)

            await self.app(scope, receive, observe)

    def _refresh_expiry(self, cookies, names) -> float:
        """Use the actual outgoing refresh cookie lifetime, never decode its JWT."""
        if names.count("refresh_token_lf") != 1:
            raise PrivateSessionError()
        refresh = cookies["refresh_token_lf"]
        if not refresh.value or not refresh["expires"]:
            raise PrivateSessionError()
        expires = parsedate_to_datetime(refresh["expires"])
        if expires.tzinfo is None:
            raise PrivateSessionError()
        return expires.timestamp()

    def _cookie_headers(self, cookie: SecretStr | None, expiry=None):
        response = Response()
        if cookie is None:
            response.delete_cookie(
                self.cookie_name, path="/", httponly=True, samesite="lax"
            )
        else:
            response.set_cookie(
                self.cookie_name,
                cookie.get_secret_value(),
                expires=datetime.fromtimestamp(expiry, timezone.utc),
                path="/",
                httponly=True,
                samesite="lax",
                secure=False,
            )
        return [
            (name, value)
            for name, value in response.raw_headers
            if name == b"set-cookie"
        ]

    async def _refuse(self, scope, receive, send, status, code):
        await JSONResponse(
            {"code": code}, status_code=status, headers={"Cache-Control": "no-store"}
        )(scope, receive, send)
