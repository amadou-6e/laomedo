"""Commands target interfaces for provider migration (#277)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from laomedo.agents.agents.base.models.commands import CommandRequest, CommandResult
    from laomedo.agents.agents.base.models.runtime import (
        CancellationObservation,
        CleanupObservation,
    )


class BaseCommandExecutor(ABC):
    """Claude/OpenCode isolated worker jobs; CodexExecServer is a separate role."""

    @abstractmethod
    def execute(self, request: CommandRequest) -> CommandResult:
        """Admit bounded work and distinguish exit from exact worker cleanup."""

    @abstractmethod
    def request_cancel(self) -> CancellationObservation:
        """Stop admission and signal owned jobs at existing provider timing."""

    @abstractmethod
    def shutdown(self) -> CleanupObservation:
        """Drain workers and close transport, preserving cleanup uncertainty."""
