"""Canonical private working-state inputs and preparation results."""

from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field


class WorkspacePaths(BaseModel):
    """Group the admitted source and owned run directory without filesystem effects."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    source: Path = Field(
        repr=False,
        exclude=True,
        description="Trusted host source; preparation checks its actual state.",
    )
    directory: Path = Field(
        repr=False,
        exclude=True,
        description="New run-owned working directory; never overwrite an existing directory.",
    )


class WorkspaceSnapshot(BaseModel):
    """Observed preparation result, distinct from authority to execute or publish."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    source_hash: str = Field(
        description="Existing canonical file-tree hash, preserving its serialized format."
    )
    baseline: str | None = Field(
        default=None,
        description="Observed source commit for Git mode; absent for a copied directory.",
    )
