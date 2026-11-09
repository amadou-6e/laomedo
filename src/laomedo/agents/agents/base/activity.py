"""Activity target interfaces for provider migration (#277)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from laomedo.agents.activity.models import ActivityProjection


class BaseActivityProjector(ABC):
    """Read-time native interpretation, separate from live terminal evidence."""

    usage_first_payload: ClassVar[bool] = False

    @classmethod
    @abstractmethod
    def accepts(cls, events: list[dict]) -> bool:
        """Recognize unqualified receipts; explicit persisted provider wins."""

    @abstractmethod
    def project(
        self,
        events: list[dict],
        *,
        root_thread: str | None = None,
        model: str | None = None,
    ) -> ActivityProjection:
        """Project native provenance with unknown usage/cost distinct from zero."""
