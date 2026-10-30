"""Expose the authenticated local runner HTTP interface."""

from __future__ import annotations

from http.server import ThreadingHTTPServer

from .handler import RunnerRequestHandler
from laomedo.agents.agents.base.agent import BaseAgent
from laomedo.agents.agents.base.settings import Settings
from laomedo.agents.errors import RunnerError


class RunnerServer(ThreadingHTTPServer):
    """Expose one explicitly configured Agent through the existing local API."""

    def __init__(
        self,
        runner: BaseAgent,
        host: str = "127.0.0.1",
        port: int = 8765,
    ):
        """Bind a loopback listener and preserve the configured startup gate.

        The caller owns serving and shutdown. Binding does not submit Agent work;
        startup cancellation is reconciled before readiness is published.
        """

        if host not in ("127.0.0.1", "::1"):
            raise RunnerError("loopback_only")


        self.runner = runner
        gate = Settings().startup_gate
        if gate:
            from laomedo.host.runner.startup import startup_gate

            with startup_gate(gate) as listening:
                if listening.with_suffix(".cancel").exists():
                    listening.with_suffix(".cancelled").touch()
                    raise SystemExit(0)
                super().__init__((host, port), RunnerRequestHandler)
                listening.touch()
                return
        super().__init__((host, port), RunnerRequestHandler)
