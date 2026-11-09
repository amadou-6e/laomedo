"""Resources target interfaces for provider migration (#277)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from laomedo.agents.agents.base.models.runtime import (
        CleanupObservation,
        ResourceBinding,
    )
    from py_docker.sessions.models import ContainerSession
    from py_docker.streams.models import Line


class ControllerStream(Protocol):
    """Borrowed native I/O only: no close, container identity or credentials."""

    def write(self, data: bytes) -> None:
        """Write through the launched controller's bounded native stdin."""

    def read_line(self) -> Line | None:
        """Read a native channel-tagged line, or EOF; EOF is not completion."""


class BaseRuntimeResource(ABC):
    """One allocated resource in the shared runtime's dependency-ordered plan."""

    @property
    @abstractmethod
    def binding(self) -> ResourceBinding:
        """Expose typed dependency inputs; host-only secrets stay excluded."""

    @abstractmethod
    def close(self, cause: BaseException | None = None) -> CleanupObservation:
        """Close only this resource; return uncertainty without hiding the cause."""


@runtime_checkable
class ContainerBuilder(Protocol):
    """Build an admitted Docker request; shared runtime performs allocation."""

    def __call__(self, bindings: Mapping[str, ResourceBinding]) -> ContainerSession:
        """Resolve earlier dependency bindings into a native session specification."""


@runtime_checkable
class OwnedResourceBuilder(Protocol):
    """Allocate a non-Docker broker/telemetry resource under shared rollback."""

    def __call__(self, bindings: Mapping[str, ResourceBinding]) -> BaseRuntimeResource:
        """Return one owned non-Docker resource with its exact close contract."""
