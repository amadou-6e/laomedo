"""Credential-owning mediator HTTP process, separate from lease supervision.

The host application must supply a reviewed transport and start this as an
independent process. This class intentionally has no ambient `gh` fallback or
credential-loading CLI. A real scoped identity is a separate deployment gate.
"""

from __future__ import annotations

from http.server import ThreadingHTTPServer

from .github_mediation import MediationStore
from .lease_service import _handler


class MediationHTTPService:
    def __init__(self, store: MediationStore, transport, *, host="127.0.0.1", port=0):
        if transport is None:
            raise ValueError("credential_transport_required")
        self.server = ThreadingHTTPServer((host, port),
                                          _handler(None, store, transport))

    @property
    def port(self):
        return self.server.server_address[1]

    def serve(self):
        self.server.serve_forever()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
