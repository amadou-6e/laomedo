"""Keep parallel loopback profile previews from replacing each other's login."""

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
        pairs = []
        owned = {name.encode("ascii") for name in PROFILE_COOKIE_NAMES}
        prefix = self.prefix.encode("ascii")
        headers = []
        for header, value in scope["headers"]:
            if header.lower() != b"cookie":
                headers.append((header, value))
                continue
            for pair in value.split(b";"):
                key, separator, content = pair.partition(b"=")
                name = key.strip()
                if name in owned:
                    continue
                if name.startswith(b"laomedo_profile_"):
                    if name.startswith(prefix) and name[len(prefix) :] in owned:
                        pairs.append(name[len(prefix) :] + separator + content)
                    continue
                # Keep unrelated raw pairs byte-for-byte. Parsing or quoting
                # their names/values would impose a new cookie format policy.
                pairs.append(pair)
        if pairs:
            headers.append((b"cookie", b";".join(pairs)))
        await self.app(
            {**scope, "headers": headers},
            receive,
            ProfileCookieResponse(send, self.prefix),
        )
