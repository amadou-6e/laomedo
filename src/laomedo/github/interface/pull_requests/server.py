"""Loopback backend for live PR reads and existing scoped operation grants."""

from http.server import ThreadingHTTPServer
from laomedo.github.interface.pull_requests.handler import PullRequestHandler


class PullRequestServer(ThreadingHTTPServer):
    """Own the private loopback listener and instance-local service bindings."""

    def __init__(self, gateway, token, port=8784, host="127.0.0.1"):
        if host != "127.0.0.1" or not isinstance(token, str) or len(token) < 32:
            raise ValueError("private_pr_service_required")
        self.gateway = gateway
        self._token = token
        super().__init__((host, port), PullRequestHandler)
