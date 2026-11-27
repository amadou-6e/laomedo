"""Loopback lease and mediation HTTP listener ownership."""

from __future__ import annotations

from http.server import ThreadingHTTPServer
from typing import TYPE_CHECKING

from laomedo.host.leases.handler import LeaseRequestHandler

if TYPE_CHECKING:
    from laomedo.host.leases.grants import GrantBook
    from laomedo.host.mediation.store import MediationStore


class LeaseHTTPServer(ThreadingHTTPServer):
    """Retain the existing request dependencies on their owning listener."""

    def __init__(
        self,
        book: GrantBook | None,
        mediator: MediationStore | None = None,
        transport=None,
        instance: str | None = None,
        *,
        host="127.0.0.1",
        port=0,
    ):
        """Bind the endpoint with dependencies ready before framework setup.

        Parameters are the existing grant book, optional mediator and transport,
        service instance and listener address. No admission or policy is changed.
        """
        self.book = book
        self.mediator = mediator
        self.transport = transport
        self.instance = instance
        super().__init__((host, port), LeaseRequestHandler)
