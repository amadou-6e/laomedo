"""Selected immutable file references after artifact admission."""

from pydantic import BaseModel, ConfigDict, Field


class ArtifactReference(BaseModel):
    """Run-bound bytes and their admitted destination; not a filesystem capability."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    provider: str = Field(description="Source provider admitted by artifact selection.")
    run_id: str = Field(description="Canonical UUID of the completed source run.")
    snapshot_hash: str = Field(
        description="Verified immutable source snapshot identity."
    )
    path: str = Field(
        description="Admitted relative source path, excluding protected material."
    )
    content_hash: str = Field(
        description="Verified canonical hash of the selected file bytes."
    )
    destination: str = Field(
        description="Admitted relative handoff destination without collisions."
    )
