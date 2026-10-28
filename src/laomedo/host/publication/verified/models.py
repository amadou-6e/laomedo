"""Implementation owned by host / publication / verified / models."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class VerifiedStage(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )

    run_id: str
    attempt_id: str
    repository: str
    branch: str
    baseline: str
    commit: str
    bundle_sha256: str
    stage_digest: str
    bundle: bytes = Field(repr=False)
