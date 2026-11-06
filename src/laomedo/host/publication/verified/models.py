"""Implementation owned by host / publication / verified / models."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
import hashlib
import json


class VerifiedStage(BaseModel):
    """Verified candidate bytes and their admitted publication identity."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )

    run_id: str = Field(description="Run whose frozen candidate was verified.")
    attempt_id: str = Field(
        description="Verification attempt that produced this stage."
    )
    repository: str = Field(description="Admitted publication repository.")
    branch: str = Field(description="Admitted source branch.")
    baseline: str = Field(description="Verified immutable baseline commit.")
    commit: str = Field(description="Verified immutable candidate commit.")
    bundle_sha256: str = Field(description="Exact verified output bundle byte hash.")
    stage_digest: str = Field(
        description="Existing canonical verified identity digest."
    )
    bundle: bytes = Field(
        repr=False, description="Verified output bytes; never raw credentials."
    )

    @classmethod
    def from_identity(
        cls, identity: VerifiedStageIdentity, bundle: bytes
    ) -> VerifiedStage:
        """Keep the verified identity grouped until the returned stage is constructed."""
        return cls(
            run_id=identity.run_id,
            attempt_id=identity.attempt_id,
            repository=identity.repository,
            branch=identity.branch,
            baseline=identity.baseline,
            commit=identity.commit,
            bundle_sha256=identity.verified_bundle_sha256,
            stage_digest=identity.digest(),
            bundle=bundle,
        )


class VerifiedStageIdentity(BaseModel):
    """Exact canonical digest preimage, separate from retained bundle bytes."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    run_id: str = Field(description="Admitted publication run identity.")
    attempt_id: str = Field(description="Admitted verification attempt identity.")
    run_binding_sha256: str | None = Field(
        default=None,
        description="Active run binding digest, omitted for a frozen record binding.",
    )
    run_record_sha256: str | None = Field(
        default=None,
        description="Frozen run record digest, omitted for an active binding.",
    )
    repository: str = Field(description="Admitted publication repository.")
    branch: str = Field(description="Admitted publication source branch.")
    baseline: str = Field(description="Verified baseline commit.")
    commit: str = Field(description="Verified candidate commit.")
    source_bundle_sha256: str = Field(
        description="Verified frozen source bundle byte hash."
    )
    verified_bundle_sha256: str = Field(description="Verified output bundle byte hash.")

    def to_payload(self) -> dict:
        """Preserve the existing single binding key and all exact hash inputs."""
        return self.model_dump(exclude_unset=True)

    def digest(self) -> str:
        """Keep the existing ASCII-escaped canonical JSON and unprefixed SHA-256."""
        return hashlib.sha256(
            json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
