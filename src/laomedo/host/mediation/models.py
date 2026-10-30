"""Host-owned mediation metadata, separate from effect and credential custody."""

from pydantic import BaseModel, ConfigDict, Field


class MediationServiceRecord(BaseModel):
    """New local discovery metadata, containing no authorization token."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    pid: int = Field(description="Owning host service process identity.")
    port: int = Field(description="Bound local mediator HTTP port.")
    module_root: str | None = Field(
        default=None,
        description="Installed package root when supplied by combined host startup.",
    )
    instance: str = Field(description="Exact fresh mediator instance identity.")
    started_at: int | float = Field(description="Observed wall-clock startup time.")
    connection_id: str = Field(
        description="Safe selected GitHub connection identity, never its credential."
    )
    generation: int = Field(description="Selected connection generation.")
    repository: str = Field(description="Configured owner/repository identity.")

    def to_record(self) -> dict:
        """Keep optional package-root omission in the standalone CLI variant."""
        return self.model_dump(exclude_unset=True)


class AuthorizedLeaseScope(BaseModel):
    """Trusted authority callback result; constructing it grants nothing."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    invocation_id: str = Field(description="Admitted authorization invocation.")
    repository: str = Field(description="Exact authorized owner/repository.")
    branch: str | None = Field(
        description="Existing authorized branch binding, nullable for non-branch operations."
    )
    base_branch: str | None = Field(
        default=None,
        description="Existing optional base binding; omission is preserved.",
    )
    operations: set[str] = Field(
        description="Admitted operation set in the existing private Python callback contract."
    )
    approval_identity: str = Field(
        description="Existing host-supplied review identity."
    )
    connection_id: str | None = Field(
        description="Safe connection identity, explicitly null for existing unconnected approvals."
    )
    connection_generation: int | None = Field(
        description="Admitted connection generation, explicitly null when no connection is bound."
    )
    target_prs: dict[int, str] = Field(
        description="Exact PR-number to base-branch targets, preserving integer keys."
    )

    def to_record(self) -> dict:
        """Preserve Python sets, integer keys and absence; no JSON coercion here."""
        return self.model_dump(exclude_unset=True)
