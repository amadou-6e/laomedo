"""New bundle journal construction; mutable diagnostics remain service-owned."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ContainerStageRecord(BaseModel):
    """Initial isolated-stage observations before container effects begin."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    status: Literal["unknown"] = Field(
        default="unknown",
        description="No container verification outcome has been observed.",
    )
    exit_code: None = Field(
        default=None, description="No native process exit has been observed."
    )
    cleanup_verified: Literal[False] = Field(
        default=False, description="Cleanup is not asserted before it occurs."
    )
    output_sha256: None = Field(
        default=None, description="No exported output digest has been observed."
    )
    output_bytes: None = Field(
        default=None, description="No exported output size has been observed."
    )
    stage_markers: list[str] = Field(
        default_factory=list,
        description="Initial empty set of observed stage-marker lines.",
    )
    success_marker_seen: Literal[False] = Field(
        default=False, description="No successful stage marker has been observed."
    )
    export_class: None = Field(
        default=None, description="No export attempt classification has been observed."
    )

    def to_record(self) -> dict:
        """Preserve the initial eight-field journal without inferring later outcomes."""
        return self.model_dump()


class BundleVerificationRecord(BaseModel):
    """Admitted new verification identity before the stage executes."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    run_id: str = Field(
        description="Admitted run whose frozen bundle is being verified."
    )
    attempt_id: str = Field(description="Fresh verification attempt identity.")
    status: Literal["unknown"] = Field(
        default="unknown",
        description="Initial outcome before the native stage executes.",
    )
    source_bundle_sha256: str = Field(
        description="Previously verified frozen source bundle digest."
    )
    baseline_bundle_sha256: str = Field(
        description="Independently verified expected baseline bundle digest."
    )
    baseline: str = Field(description="Admitted immutable baseline commit.")
    commit: str = Field(description="Admitted candidate commit.")
    image_id: str = Field(description="Pinned approved verifier image identity.")
    policy_approved: Literal[False] = Field(
        default=False,
        description="Execution does not infer separate publication approval.",
    )

    def to_record(self) -> dict:
        """Return the existing nine-field initial verification journal."""
        return self.model_dump()
