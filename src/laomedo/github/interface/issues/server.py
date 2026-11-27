"""Loopback backend for live issue reads and existing scoped operation grants."""

from http.server import ThreadingHTTPServer
from laomedo.github.interface.issues.handler import IssueRequestHandler


class IssueServer(ThreadingHTTPServer):
    """Own the private loopback listener and instance-local service bindings."""

    def __init__(
        self, gateway, token, port=8783, host="127.0.0.1", *, public_only=False
    ):
        if host != "127.0.0.1" or not isinstance(token, str) or len(token) < 32:
            raise ValueError("private_issue_service_required")
        if public_only:
            from laomedo.github.transport.rest.public import PublicGitHubIssueTransport

            if not gateway.transports or any(
                type(item) is not PublicGitHubIssueTransport
                for item in gateway.transports.values()
            ):
                raise ValueError("public_issue_transport_required")
        self.gateway = gateway
        self._token = token
        self.public_only = public_only
        super().__init__((host, port), IssueRequestHandler)
