"""Catalog target interfaces for provider migration (#277)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from laomedo.agents.agents.base.models.catalog import ModelCatalogSnapshot


class BaseModelCatalog(ABC):
    """Common zero-turn discovery; native caching/admission stays composed."""

    @abstractmethod
    def discover(self, *, refresh: bool = False) -> ModelCatalogSnapshot:
        """Return advertised choices without inference or selection substitution."""
