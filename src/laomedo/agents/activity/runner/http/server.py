"""Listener with an explicit typed owner; lifecycle remains with its caller."""
from __future__ import annotations

from http.server import ThreadingHTTPServer
from typing import TYPE_CHECKING
from .handler import LaunchTelemetryRequestHandler

if TYPE_CHECKING:
    from laomedo.agents.activity.runner.telemetry import LaunchTelemetry


class LaunchTelemetryHttpServer(ThreadingHTTPServer):
    """Bind the existing handler to this server's owner instance."""

    def __init__(self, owner: "LaunchTelemetry", address, *, provenance, request_types):
        """Bind the supplied address; the existing caller starts and stops serving."""
        self.owner = owner
        self.provenance = provenance
        self.request_types = request_types
        super().__init__(address, LaunchTelemetryRequestHandler)
