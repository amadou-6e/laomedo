"""Saved-account graph-run contracts; none is a reusable credential or grant."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from laomedo.github.connections.models import (
    GitHubConnectionScope,
    GitHubReadAuthorization,
    GitHubRepositoryIdentity,
)


class GitHubNodeReadRequest(BaseModel):
    """Private browser input; owner and credential authority are never accepted."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    connection_id: UUID = Field(
        description="Explicit saved connection selected in this profile."
    )
    kind: Literal["issue", "pr"] = Field(description="Existing node read capability.")
    repository_url: str = Field(
        strict=True,
        max_length=1024,
        description="Exact selected GitHub repository URL; consent is revalidated on the host.",
    )
    labels: list[str] = Field(
        max_length=100,
        description="Current all-label filter, validated by the canonical gateway.",
    )
    state: Literal["open", "closed", "merged", "all"] = Field(
        description="Current node state filter; merged is PR-only."
    )
    number: int | None = Field(
        default=None,
        strict=True,
        gt=0,
        le=2**53 - 1,
        description="Exact selected target for inspection; absent for discovery.",
    )


class GitHubWorkerReadRequest(BaseModel):
    """Worker read selectors; broker authority supplies all credential bounds."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    job_id: UUID = Field(description="Exact admitted isolated job, not authentication.")
    vertex_id: str = Field(
        strict=True,
        min_length=1,
        max_length=256,
        description="Exact admitted GitHub node within this job.",
    )
    labels: list[str] = Field(
        max_length=100,
        description="Existing all-label read filter; never an authorization bound.",
    )
    state: Literal["open", "closed", "merged", "all"] = Field(
        description="Existing node read filter; merged is valid only for PRs."
    )
    number: int | None = Field(
        default=None,
        strict=True,
        gt=0,
        le=2**53 - 1,
        description="Runtime read reference; must match any broker-held picker target.",
    )


class GitHubNodeReadResult(BaseModel):
    """Buffered browser read and its exact host-only response release fence."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    authorization: GitHubReadAuthorization = Field(
        exclude=True,
        repr=False,
        description="Current account/repository authority for response release only.",
    )
    payload: dict = Field(
        repr=False,
        description="Existing Issue/PR gateway read payload, containing no credential.",
    )


class GitHubNodeSelection(BaseModel):
    """One graph vertex's exact account/repository and potential write targets."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    vertex_id: str = Field(
        strict=True,
        min_length=1,
        max_length=256,
        description="Exact native graph vertex ID.",
    )
    kind: Literal["issue", "pr"] = Field(description="Existing GitHub node capability.")
    connection_id: UUID = Field(
        description="Explicit saved account selection, never an ambient default."
    )
    repository: GitHubRepositoryIdentity = Field(
        description="Consented numeric identity and confirmed repository location."
    )
    number: int | None = Field(
        default=None,
        strict=True,
        gt=0,
        le=2**53 - 1,
        description="Exact Issue/PR target; absent only for discovery or untargeted reads.",
    )
    operations: tuple[Literal["modify", "close"], ...] = Field(
        default=(),
        description="Operation kinds shown in the one-per-run approval, not a grant.",
    )

    @model_validator(mode="after")
    def exact_write_target(self):
        """Refuse broad or duplicate operation approval without an exact target."""
        if len(set(self.operations)) != len(self.operations) or (
            self.operations and self.number is None
        ):
            raise ValueError("github_node_target_invalid")
        return self


class GitHubNodeAdmission(BaseModel):
    """Selection plus online-verified generation; it contains no credential."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    selection: GitHubNodeSelection = Field(
        description="Exact graph selection verified during preparation."
    )
    generation: int = Field(
        strict=True,
        gt=0,
        description="Verified connection generation; reconnect requires a new run.",
    )


class GitHubWorkerLease(BaseModel):
    """Broker-only hashed capability and the admitted job's real timeout backstop."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    digest: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        exclude=True,
        repr=False,
        description="SHA-256 of a job capability; the clear capability is not retained.",
    )
    expires_at: float = Field(
        strict=True,
        gt=0,
        allow_inf_nan=False,
        description="Absolute broker monotonic deadline from the native job timeout.",
    )


class GitHubNodeRun(BaseModel):
    """In-memory native job binding, never parsed from browser or graph JSON."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    reference: SecretStr = Field(
        exclude=True, repr=False, description="Broker-only opaque run reference."
    )

    scope: GitHubConnectionScope = Field(
        exclude=True,
        repr=False,
        description="Trusted initiating owner/lease revalidation callback.",
    )
    flow_id: UUID = Field(description="Native flow admitted by its authenticated host.")
    job_id: UUID = Field(description="Native job bound after explicit run admission.")
    graph_digest: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="Exact executable graph approved for this job.",
    )
    nodes: tuple[GitHubNodeAdmission, ...] = Field(
        min_length=1, description="Verified exact node admissions for this graph."
    )
    worker_deadline: float | None = Field(
        default=None,
        strict=True,
        gt=0,
        allow_inf_nan=False,
        description="First issued worker's native job deadline; key rotation cannot extend it.",
    )

    def node_for_vertex(self, vertex_id):
        """Return the admitted node bound to one native vertex, or None."""
        return next(
            (node for node in self.nodes if node.selection.vertex_id == vertex_id),
            None,
        )
