"""Codex provider implementation of canonical Activity projection."""

from laomedo.agents.agents.base.interim import BaseActivityProjector
from laomedo.agents.activity.models import ActivityProjection
from laomedo.agents.agents.codex.activity.projection import project


class CodexActivityProjector(BaseActivityProjector):
    """Keep native interpretation behind a provider-qualified typed contract."""

    @classmethod
    def accepts(cls, events) -> bool:
        """Recognize native receipts only for unqualified internal projection callers."""
        return True

    def project(self, events, *, root_thread=None, model=None) -> ActivityProjection:
        """Return canonical values without dispatching work or inventing usage."""
        return project(events, root_thread=root_thread, model=model)
