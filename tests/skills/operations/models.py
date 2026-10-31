"""Grouped state for one isolated internal operation scenario."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from laomedo.skills.registry.store import SkillStore
from laomedo.skills.operations.service import SkillOperations


class SkillOperationCase(BaseModel):
    """One test's mutable inputs and actual isolated operation service."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    root: Path = Field(description="Caller-owned temporary root for all scenario state")
    original: str = Field(description="Initial SKILL.md bytes expressed as UTF-8 text")
    store: SkillStore = Field(
        exclude=True, repr=False, description="Isolated registry used by this case"
    )
    initial: dict[str, Any] = Field(
        description="Actual imported immutable starting reference"
    )
    policy: dict[str, Any] = Field(
        description="Raw edit policy, deliberately available for invalid-input controls"
    )
    service: SkillOperations = Field(
        exclude=True,
        repr=False,
        description="Operation service owning this case's journal",
    )
    operation: dict[str, Any] = Field(
        description="Raw multi-file edit proposal submitted to the production boundary"
    )

    def prepare(self, revision=None, commit=""):
        """Reserve this case's exact initial or supplied revision; propagate errors."""
        return self.service.prepare(
            "internal-test", revision or self.initial["revision_id"], commit
        )
