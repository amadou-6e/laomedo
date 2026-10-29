"""Listener with an explicit typed owner; lifecycle remains with its caller."""
from __future__ import annotations

from http.server import ThreadingHTTPServer
from typing import TYPE_CHECKING
from .handler import CommandRequestHandler

if TYPE_CHECKING:
    from laomedo.agents.agents.claude.container import CommandService


class CommandHttpServer(ThreadingHTTPServer):
    """Bind the existing handler to this server's owner instance."""

    def __init__(self, owner: "CommandService", address):
        """Bind the supplied address; the existing caller starts and stops serving."""
        self.owner = owner
        super().__init__(address, CommandRequestHandler)
