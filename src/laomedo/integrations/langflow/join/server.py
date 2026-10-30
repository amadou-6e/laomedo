"""Implementation owned by integrations / langflow / join / server."""

from __future__ import annotations
from http.server import ThreadingHTTPServer
from laomedo.integrations.langflow.join.handler import JoinRequestHandler


class JoinServer(ThreadingHTTPServer):
    def __init__(self, controller, token, *, port, host="127.0.0.1"):
        """Construct an authenticated bridge; caller owns its lifecycle."""
        if not isinstance(token, str) or not token or not 0 <= port <= 65535:
            raise ValueError("join_server_config_invalid")
        if host != "127.0.0.1":
            raise ValueError("join_server_must_bind_loopback")

        self.controller = controller
        self.token = token
        super().__init__((host, port), JoinRequestHandler)
