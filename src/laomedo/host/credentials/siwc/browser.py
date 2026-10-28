"""Implementation owned by host / credentials / siwc / browser."""

from __future__ import annotations

from functools import partial
from laomedo.host.credentials.siwc.callback import CallbackHandler
from http.server import HTTPServer
from urllib.parse import parse_qs
from urllib.parse import urlsplit
import laomedo.host.credentials.siwc.errors as _siwc_errors
import webbrowser


def browser_connect(
    store: _siwc_connection.ChatGPTConnection, *, client_id=None, timeout=180
) -> dict:
    """Open the system browser and handle one loopback OAuth callback."""
    import laomedo.host.credentials.siwc.connection as _siwc_connection

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
            raise _siwc_errors.AuthError("auth_browser_unavailable")
        server.handle_request()
    if not received:
        raise _siwc_errors.AuthError("auth_callback_timeout")
    return store.finish(attempt, received)
