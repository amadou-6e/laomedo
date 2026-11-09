"""Opencode provider implementation of canonical Activity projection."""

from laomedo.agents.agents.base.base.interim import BaseActivityProjector
from laomedo.agents.activity.models import ActivityProjection
from laomedo.agents.agents.opencode.activity.projection import project


class OpenCodeActivityProjector(BaseActivityProjector):
    """Keep native interpretation behind a provider-qualified typed contract."""

    usage_first_payload = True

    @classmethod
    def accepts(cls, events) -> bool:
        """Recognize native receipts only for unqualified internal projection callers."""
        return any(
            str(row["raw"].get("event", row["raw"]).get("method", "")).startswith(
                "opencode/"
            )
            for row in events
        )

    def project(self, events, *, root_thread=None, model=None) -> ActivityProjection:
        """Return canonical values without dispatching work or inventing usage."""
        return ActivityProjection.model_validate(
            project(events, root_thread=root_thread, model=model)
        )
