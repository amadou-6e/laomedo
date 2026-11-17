"""Keep parallel loopback profile previews from replacing each other's login."""

from http.cookies import SimpleCookie

from starlette.requests import HTTPConnection

from laomedo.integrations.langflow.local_profiles.settings import PROFILE_COOKIE_NAMES


class ProfileCookieResponse:
    """Rename only owned auth cookies without altering their security attributes."""

    def __init__(self, send, prefix):
        self.send = send
        self.prefix = prefix.encode("ascii")

    async def __call__(self, message):
        if message["type"] == "http.response.start":
            headers = []
            for name, value in message.get("headers", []):
                if name.lower() == b"set-cookie":
                    key, separator, rest = value.partition(b"=")
                    if key.decode("latin-1") in PROFILE_COOKIE_NAMES:
                        value = self.prefix + key + separator + rest
                headers.append((name, value))
            message = {**message, "headers": headers}
        await self.send(message)


class ProfileCookieBoundary:
    """Translate this port's browser cookies before any profile/auth consumer.

    Canonical unscoped cookies are deliberately ignored: they could belong to
    another preview. No credential fallback or migration is safe across ports.
    HTTP and WebSocket consumers retain the upstream canonical cookie names.
    """

    def __init__(self, app, *, port):
        self.app = app
        self.prefix = f"laomedo_profile_{port}_"

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        cookies = HTTPConnection(scope).cookies
        translated = SimpleCookie()
        selected = {self.prefix + name for name in PROFILE_COOKIE_NAMES}
        for name, value in cookies.items():
            if name not in PROFILE_COOKIE_NAMES and name not in selected:
                translated[name] = value
        for name in PROFILE_COOKIE_NAMES:
            scoped = self.prefix + name
            if scoped in cookies:
                translated[name] = cookies[scoped]
        headers = [
            (name, value)
            for name, value in scope["headers"]
            if name.lower() != b"cookie"
        ]
        if translated:
            headers.append(
                (
                    b"cookie",
                    translated.output(header="", sep=";").strip().encode("latin-1"),
                )
            )
        await self.app(
            {**scope, "headers": headers},
            receive,
            ProfileCookieResponse(send, self.prefix),
        )
