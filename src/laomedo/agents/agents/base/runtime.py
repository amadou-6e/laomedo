"""Target runtime ABC and shared py-docker mechanisms; scopes migrate later."""

from __future__ import annotations

from abc import ABC, abstractmethod
from laomedo.agents.agents.base.contracts import ControllerStream
from laomedo.agents.agents.base.models import (
    RuntimeLaunchRequest,
    RuntimeObservation,
    RuntimeCleanupReport,
    CleanupObservation,
    ResourcePlan,
)
from laomedo.agents.errors import RunnerError

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
import threading
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from py_docker import Client
    from py_docker.connection.settings import ConnectionSettings
    from py_docker.execution.models import CommandResult as DockerCommandResult
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
    ) -> "DockerCommandResult":
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


class BaseAgentRuntime(ABC):
    """Single-use Docker scope; common mechanisms will implement this contract.

    Session operations stay on the creator thread. No ACP/native conversation
    methods belong here. Claude may create multiple scopes in one attempt.
    """

    @abstractmethod
    def prepare(self, request: RuntimeLaunchRequest) -> RuntimeObservation:
        """Admit/build dependencies without launching the controller.

        Failure rolls back started resources, caches a closed cleanup report and
        raises the provider-mapped RunnerError retaining its primary observation.
        """

    @abstractmethod
    def launch(self) -> RuntimeObservation:
        """Launch the prepared controller; launch is not ACP readiness.

        Resolve specs from prior typed resource bindings. Apply the same rollback
        and closed-report guarantee as prepare on any partial-launch failure.
        """

    @abstractmethod
    def run_job(
        self,
        job: ContainerJob,
        *,
        cancelled: threading.Event | None = None,
        deadline: float | None = None,
        cleanup_seconds: float | None = None,
    ) -> DockerCommandResult:
        """Run in prepared/launched scope, never after closure.

        Register receipts under the runtime admission lock before dispatch; map
        native errors at the provider boundary. Self-contained worker calls own
        their clients and do not borrow a creator-thread controller session.
        """

    @abstractmethod
    def controller_stream(self) -> ControllerStream:
        """Borrow launched I/O without handing protocol code cleanup ownership."""

    @abstractmethod
    def close_controller(
        self, cause: BaseException | None = None
    ) -> CleanupObservation:
        """Quiesce only declared steps, exit monitor and close controller.

        Return cached uncertainty rather than raise. Run while the owning event
        loop is live, before ACP disconnect and its blocking reader shutdown.
        """

    @abstractmethod
    def shutdown(self, cause: BaseException | None = None) -> RuntimeCleanupReport:
        """Close controller if needed and remaining resources after disconnect.

        Return per-resource uncertainty, never a success-only placeholder or a
        cleanup exception. Repeated shutdown returns the same settled report.
        """

    @abstractmethod
    def _resource_plan(self, request: RuntimeLaunchRequest) -> ResourcePlan:
        """Supply provider topology/builders; shared code owns allocation/rollback."""

    @abstractmethod
    def _map_docker_failure(self, error: Exception, *, stage: str) -> RunnerError:
        """Preserve the provider's stable boundary code and safe primary evidence."""
