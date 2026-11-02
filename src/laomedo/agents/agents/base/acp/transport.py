"""One blocking-to-async bridge; the SDK owns JSON-RPC request multiplexing."""

import asyncio
import json

from acp.schema import RequestPermissionRequest, SessionNotification


class DockerTransport:
    """Adapt an owned py-docker session without granting host execution access.

    Parameters
    ----------
    session : py_docker.sessions.session.Session
        Already launched session. Its creator retains all lifecycle ownership.
    """

    def __init__(self, session, *, on_failure=None):
        """Retain the session; never open a second container or Docker endpoint."""
        self.session = session
        self.on_failure = on_failure

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
        try:
            while (line := await asyncio.to_thread(self.session.read_line)) is not None:
                if line.channel == "stderr":
                    continue
                value = json.loads(line.data)
                self._validate(value)
                return value
        except Exception:
            # SDK 0.12 logs receive/notification exceptions through the root
            # logger. Disconnect without passing private input or its traceback
            # to that logger; the owning session must fail the turn.
            if self.on_failure is not None:
                self.on_failure()
        return None

    def _validate(self, message):
        """Validate SDK-bound inputs before its diagnostic exception handlers."""
        if not isinstance(message, dict):
            raise ValueError("Invalid ACP frame")
        if "id" in message and type(message["id"]) not in (str, int):
            raise ValueError("Invalid ACP identity")
        if "method" not in message:
            error = message.get("error")
            if error is not None and (
                not isinstance(error, dict)
                or type(error.get("code")) is not int
                or not isinstance(error.get("message"), str)
            ):
                raise ValueError("Invalid ACP error")
            return
        method = message["method"]
        if not isinstance(method, str):
            raise ValueError("Invalid ACP method")
        params = message.get("params")
        if method == "session/update" and "id" not in message:
            SessionNotification.model_validate(params)
        elif method == "session/request_permission" and "id" in message:
            RequestPermissionRequest.model_validate(params)
        elif method.startswith("_"):
            if not isinstance(params, dict):
                raise ValueError("Invalid ACP extension")
        elif "id" not in message:
            raise ValueError("Unsupported ACP notification")

    async def close(self) -> None:
        """Leave exact-ID teardown to the session's creator, never detach it here."""
