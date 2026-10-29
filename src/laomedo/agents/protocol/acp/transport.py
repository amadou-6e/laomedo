"""One blocking-to-async bridge; the SDK owns JSON-RPC request multiplexing."""

import asyncio
import json

from laomedo.agents.runtime.errors import RunnerError


class DockerTransport:
    """Adapt an owned py-docker session without granting host execution access.

    Parameters
    ----------
    session : py_docker.sessions.session.Session
        Already launched session. Its creator retains all lifecycle ownership.
    """

    def __init__(self, session):
        """Retain the session; never open a second container or Docker endpoint."""
        self.session = session

    async def send(self, message: dict) -> None:
        """Send one SDK message through the session's bounded serialized stdin."""
        await asyncio.to_thread(
            self.session.write, (json.dumps(message) + "\n").encode("utf-8")
        )

    async def receive(self) -> dict | None:
        """Read stdout protocol messages, discarding private diagnostic stderr.

        Session stream limits bound both channels. Invalid stdout is a failure;
        diagnostic output is never interpreted as a result or shown to a user.
        """
        while (line := await asyncio.to_thread(self.session.read_line)) is not None:
            if line.channel == "stderr":
                continue
            try:
                value = json.loads(line.data)
            except (ValueError, UnicodeError):
                raise RunnerError("runner_transport_failed") from None
            if not isinstance(value, dict):
                raise RunnerError("runner_transport_failed")
            return value
        return None

    async def close(self) -> None:
        """Leave exact-ID teardown to the session's creator, never detach it here."""
