"""Same-origin, bounded requests and sign-out fencing for application chat."""

import hashlib
from contextlib import suppress
from http.cookies import SimpleCookie
from urllib.parse import urlsplit

from starlette.responses import JSONResponse


class AssistantBoundary:
    """Keep private MCP and browser authority distinct while preserving unrelated app routes."""

    def __init__(self, app, *, runtime, origin):
        """Bind the trusted configured origin, never a request-supplied Host value."""
        self.app, self.runtime, self.origin = app, runtime, origin
        self.host = urlsplit(origin).netloc
        self.origins = {origin, "http://localhost:" + str(urlsplit(origin).port)}
        self.hosts = {urlsplit(item).netloc for item in self.origins}

    async def __call__(self, scope, receive, send):
        """Bound browser requests, refuse cross-origin writes and revoke before logout release."""
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"].rstrip("/")
        assistant = path.startswith("/api/v1/laomedo/assistant")
        private_mcp = path == "/api/v1/laomedo/assistant/mcp"
        logout = path == "/api/v1/logout"
        if not assistant and not logout:
            return await self.app(scope, receive, send)
        if logout:
            # The existing sign-out endpoint must remain reachable through all
            # upstream-supported hostnames and clients, including aliases.
            if self.runtime.ready:
                tokens = set()
                for name, value in scope["headers"]:
                    if name.lower() == b"authorization" and value.lower().startswith(
                        b"bearer "
                    ):
                        tokens.add(value[7:].decode("latin-1"))
                    if name.lower() == b"cookie":
                        with suppress(Exception):
                            cookies = SimpleCookie()
                            cookies.load(value.decode("latin-1"))
                            if "access_token_lf" in cookies:
                                tokens.add(cookies["access_token_lf"].value)
                for token in tokens:
                    with suppress(Exception):
                        await self.runtime.lock_session(
                            hashlib.sha256(token.encode()).hexdigest()
                        )
            return await self.app(scope, receive, send)
        headers = {}
        for name, value in scope["headers"]:
            key = name.decode("latin-1").lower()
            if key in headers and key in {
                "host",
                "origin",
                "authorization",
                "cookie",
                "content-length",
            }:
                return await self._refuse(scope, receive, send, 403)
            headers[key] = value.decode("latin-1")
        supplied_origin = headers.get("origin")
        if headers.get("host") not in self.hosts or (
            supplied_origin is not None
            and (
                supplied_origin not in self.origins
                or urlsplit(supplied_origin).netloc != headers.get("host")
            )
        ):
            return await self._refuse(scope, receive, send, 403)
        mutation = scope["method"] not in {"GET", "HEAD", "OPTIONS"}
        if not private_mcp and (
            headers.get("sec-fetch-site") not in {None, "same-origin"}
            or (mutation and supplied_origin not in self.origins)
        ):
            return await self._refuse(scope, receive, send, 403)
        if assistant and not private_mcp and mutation:
            data = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                data.extend(message.get("body", b""))
                if len(data) > 65536:
                    return await self._refuse(scope, receive, send, 413)
                if not message.get("more_body"):
                    break
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if delivered:
                    return await receive()
                delivered = True
                return {"type": "http.request", "body": bytes(data), "more_body": False}

            receive_body = bounded_receive
        else:
            receive_body = receive
        return await self.app(scope, receive_body, send)

    async def _refuse(self, scope, receive, send, status):
        """Return a stable refusal without echoing request or credential contents."""
        await JSONResponse(
            {"code": "assistant_request_refused"},
            status_code=status,
            headers={"Cache-Control": "no-store"},
        )(scope, receive, send)
