"""Listener with an explicit typed owner; lifecycle remains with its caller."""
from __future__ import annotations

from http.server import ThreadingHTTPServer
from typing import TYPE_CHECKING
from .handler import ClaudeTelemetryRequestHandler

if TYPE_CHECKING:
    from laomedo.agents.agents.claude.activity.telemetry import ClaudeTelemetry


class ClaudeTelemetryHttpServer(ThreadingHTTPServer):
    """Bind the existing handler to this server's owner instance."""

    def __init__(self, owner: "ClaudeTelemetry", address, *, request_types):
        """Bind the supplied address; the existing caller starts and stops serving."""
        self.owner = owner
        self.request_types = request_types
        super().__init__(address, ClaudeTelemetryRequestHandler)
