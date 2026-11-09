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
        from py_docker import Client

        options = {"environment": self._environment}
        if self._settings is not None:
            options["settings"] = self._settings
        with Client(**options) as client:
            yield client

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
            return client.jobs.run(
                job,
                cancelled=cancelled,
                deadline=deadline,
                cleanup_seconds=cleanup_seconds,
            )

    def recover(
        self, receipts: Sequence[Path], *, kind: Literal["session", "job"] = "session"
    ) -> None:
        """Recover caller-selected receipts, never scan or broaden their scope."""
        if kind not in {"session", "job"}:
            raise ValueError("Unknown Docker receipt kind")
        with self.client() as client:
            service = client.jobs if kind == "job" else client.sessions
            for receipt in receipts:
                service.recover(receipt)
