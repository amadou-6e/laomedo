"""Shared py-docker client, one-shot job and exact-receipt mechanisms."""

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
import threading
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from py_docker import Client
    from py_docker.connection.settings import ConnectionSettings
    from py_docker.execution.models import CommandResult
    from py_docker.jobs.models import ContainerJob
    from py_docker.sessions.models import ContainerSession
    from py_docker.sessions.session import Session
    from py_docker.containers.models import ContainerIdentity
    from py_docker.streams.models import StreamLimits


class AgentDockerMechanism:
    """Own self-contained client calls without provider policy or attempt state.

    Native exceptions propagate unchanged to the owning provider boundary. An
    admitted environment pins the selected endpoint; None retains native initial
    daemon discovery. No client or live session is shared between worker threads.
    """

    def __init__(
        self,
        environment: Mapping[str, str] | None,
        *,
        settings: "ConnectionSettings | None" = None,
    ):
        self._environment = dict(environment) if environment is not None else None
        self._settings = settings

    @contextmanager
    def client(self) -> Iterator["Client"]:
        """Open and close one native client, preserving native exception handling."""
        with self.connect() as client:
            yield client

    def connect(self) -> "Client":
        """Open a client whose explicit owner must close it.

        Long-lived provider scopes use this when their existing cleanup sequence
        cannot be expressed as one lexical client context. Connection selection
        is identical to client(); no provider constructs a separate SDK client.
        """
        from py_docker import Client

        options = {"environment": self._environment}
        if self._settings is not None:
            options["settings"] = self._settings
        return Client(**options)

    def run_job(
        self,
        job: "ContainerJob",
        *,
        cancelled: threading.Event | None = None,
        deadline: float | None = None,
        cleanup_seconds: float | None = None,
    ) -> "CommandResult":
        """Delegate exact launch, bounded output and cleanup to the native job API."""
        with self.client() as client:
            return self.execute_job(
                client,
                job,
                cancelled=cancelled,
                deadline=deadline,
                cleanup_seconds=cleanup_seconds,
            )

    @staticmethod
    def execute_job(
        client: "Client",
        job: "ContainerJob",
        *,
        cancelled: threading.Event | None = None,
        deadline: float | None = None,
        cleanup_seconds: float | None = None,
    ) -> "CommandResult":
        """Run on an explicitly borrowed client without changing its lifetime."""
        options = {}
        if cancelled is not None:
            options["cancelled"] = cancelled
        if deadline is not None:
            options["deadline"] = deadline
        if cleanup_seconds is not None:
            options["cleanup_seconds"] = cleanup_seconds
        return client.jobs.run(job, **options)

    @staticmethod
    @contextmanager
    def session(
        client: "Client",
        request: "ContainerSession",
        *,
        deadline: float | None = None,
        cleanup_seconds: float | None = None,
    ) -> Iterator["Session"]:
        """Own one interactive session on a caller-owned client.

        Enter and exit on the creator thread. Native startup, body and cleanup
        exceptions retain their identity and context-manager semantics. The
        caller closes its client after its other dependent resources; this
        scope never interprets agent readiness or a native conversation.
        """
        with AgentDockerMechanism.start_session(
            client, request, deadline=deadline, cleanup_seconds=cleanup_seconds
        ) as session:
            yield session

    @staticmethod
    def start_session(
        client: "Client",
        request: "ContainerSession",
        *,
        deadline: float | None = None,
        cleanup_seconds: float | None = None,
    ) -> "Session":
        """Launch an explicitly owned session; its owner must call close_session.

        Use session() for lexical scope ownership. This form supports a
        persistent executor whose reader must drain at its existing close point.
        """
        options = {}
        if deadline is not None:
            options["deadline"] = deadline
        if cleanup_seconds is not None:
            options["cleanup_seconds"] = cleanup_seconds
        return client.sessions.open(request, **options)

    @staticmethod
    def run_command(
        client: "Client",
        identity: "ContainerIdentity",
        command: Sequence[str],
        limits: "StreamLimits",
    ) -> "CommandResult":
        """Execute once inside an exact owned container; never retry on failure."""
        return client.execution.run(identity, command, limits)

    @staticmethod
    def close_session(session: "Session") -> None:
        """Request exact creator-thread cleanup, retaining native cached failure.

        ACP calls this before reader disconnect to unblock its read thread. The
        enclosing session scope also exits through the same native owner; native
        Session.close preserves uncertainty rather than treating a retry as OK.
        """
        session.close()

    def recover(
        self,
        receipts: Sequence[Path],
        *,
        kind: Literal["session", "job"] = "session",
    ) -> None:
        """Recover caller-selected receipts, never scan or broaden their scope."""
        if kind not in {"session", "job"}:
            raise ValueError("Unknown Docker receipt kind")
        with self.client() as client:
            self.recover_receipts(client, receipts, kind=kind)

    @staticmethod
    def recover_receipts(
        client: "Client",
        receipts: Sequence[Path],
        *,
        kind: Literal["session", "job"] = "session",
    ) -> None:
        """Recover exact receipts on a borrowed client; never broaden selection."""
        if kind not in {"session", "job"}:
            raise ValueError("Unknown Docker receipt kind")
        service = client.jobs if kind == "job" else client.sessions
        for receipt in receipts:
            service.recover(receipt)
