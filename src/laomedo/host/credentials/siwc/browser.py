"""Implementation owned by host / credentials / siwc / browser."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from laomedo.host.credentials.siwc.connection import ChatGPTConnection

from functools import partial
from laomedo.host.credentials.siwc.callback import CallbackHandler
from http.server import HTTPServer
from urllib.parse import parse_qs
from urllib.parse import urlsplit
from laomedo.host.credentials.siwc.errors import AuthError
import webbrowser


def browser_connect(store: ChatGPTConnection, *, client_id=None, timeout=180) -> dict:
    """Open the system browser and handle one loopback OAuth callback."""
    from laomedo.host.credentials.siwc.connection import ChatGPTConnection

    received = {}

    with HTTPServer(
        ("127.0.0.1", 0), partial(CallbackHandler, received=received)
    ) as server:
        server.timeout = timeout
        attempt = store.begin(
            f"http://127.0.0.1:{server.server_port}/auth/callback", client_id=client_id
        )
        # Authorization URL may contain id_token_hint. Never print or log it.
        if not webbrowser.open(attempt["url"]):
            raise AuthError("auth_browser_unavailable")
        server.handle_request()
    if not received:
        raise AuthError("auth_callback_timeout")
    return store.finish(attempt, received)
