"""Runtime target interfaces for provider migration (#277)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from laomedo.agents.agents.base.base.resources import ControllerStream
from laomedo.agents.errors import RunnerError
import threading

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from laomedo.agents.agents.base.models.runtime import (
        CleanupObservation,
        ResourcePlan,
        RuntimeCleanupReport,
        RuntimeLaunchRequest,
        RuntimeObservation,
    )
    from py_docker.execution.models import CommandResult as DockerCommandResult
    from py_docker.jobs.models import ContainerJob


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
