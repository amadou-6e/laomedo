"""Same-origin browser boundaries for local profile entry and registration."""

import re
from starlette.responses import JSONResponse


class LocalProfileBoundary:
    """An ASGI guard for loopback profile/auth entry, including picker reads.

    This does not replace authenticated authorization on other application APIs.
    Static assets remain readable; new profile state is exposed only same-origin.
    """

    def __init__(self, app, *, port: int):
        self.app = app
        self.host = f"127.0.0.1:{port}"
        self.origin = f"http://{self.host}"

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"].rstrip("/")
        method = scope["method"]
        protected = (
            path.startswith("/api/v1/laomedo/profiles")
            or path
            in {"/api/v1/login", "/api/v1/logout", "/api/v1/refresh", "/api/v1/users"}
            or bool(re.fullmatch(r"/api/v1/users/[^/]+", path))
        )
        if protected:
            headers = {}
            for name, value in scope["headers"]:
                key = name.decode("latin-1").lower()
                if key in headers and key in {"host", "origin", "sec-fetch-site"}:
                    return await self._refuse(scope, receive, send)
                headers[key] = value.decode("latin-1")
            if headers.get("host") != self.host:
                return await self._refuse(scope, receive, send)
            origin = headers.get("origin")
            if origin is not None and origin != self.origin:
                return await self._refuse(scope, receive, send)
            if headers.get("sec-fetch-site") not in {None, "same-origin"}:
                return await self._refuse(scope, receive, send)
            if method not in {"GET", "HEAD", "OPTIONS"} and origin != self.origin:
                return await self._refuse(scope, receive, send)
            if (
                path.startswith("/api/v1/laomedo/profiles")
                and method in {"GET", "HEAD"}
                and origin is None
                and headers.get("sec-fetch-site") != "same-origin"
            ):
                return await self._refuse(scope, receive, send)
            # First profile slice has no rename, password/role change or deletion.
            if path.startswith("/api/v1/users/") and method in {
                "PATCH",
                "DELETE",
                "PUT",
            }:
                return await self._refuse(scope, receive, send)
        return await self.app(scope, receive, send)

    async def _refuse(self, scope, receive, send):
        await JSONResponse(
            {"code": "profile_request_refused"},
            status_code=403,
            headers={"Cache-Control": "no-store"},
        )(scope, receive, send)
