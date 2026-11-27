"""Persisted connection identity and safe Settings projections."""

from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, JsonValue
from laomedo.agents.workspaces.models import WorkspaceChanges
from laomedo.agents.agents.base.models import VerifiedReviewProvenance
from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.connections.settings import GRAPH_NODE_TASK_BYTES
from laomedo.skills.registry.models import SkillReference


class GraphNodePolicy(BaseModel):
    """Approved native selections, with task text treated as untrusted input."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    model: str = Field(min_length=1)
    effort: str = Field(min_length=1)
    task: str = Field(repr=False)
    task_from_input: bool = False
    timeout_seconds: int = Field(default=180, ge=1, le=86400)
    skills: tuple[SkillReference, ...] = Field(default=(), max_length=16)

    def native_request(self, body, request_id):
        """Preserve permitted task data while refusing added native authority."""
        allowed = {
            "request_id",
            "task",
            "model",
            "effort",
            "skill_refs",
            "skill_ref",
            "run_timeout_seconds",
        }
        if (
            not isinstance(body, dict)
            or set(body) - allowed
            or body.get("model") != self.model
            or body.get("effort") != self.effort
            or ("skill_ref" in body and "skill_refs" in body)
            or ([body["skill_ref"]] if "skill_ref" in body else body.get("skill_refs"))
            != [reference.to_reference_payload() for reference in self.skills]
            or not isinstance(body.get("task"), str)
            or not body["task"].strip()
            or len(body["task"].encode("utf-8")) > GRAPH_NODE_TASK_BYTES
            or (not self.task_from_input and body["task"] != self.task)
        ):
            raise ProviderConnectionError("verified_review_unavailable")
        timeout = body.get("run_timeout_seconds", self.timeout_seconds)
        if type(timeout) is not int or not 1 <= timeout <= self.timeout_seconds:
            raise ProviderConnectionError("verified_review_unavailable")
        return {**body, "request_id": request_id}


class OwnedWorkspaceChanges(BaseModel):
    """A host-only projection bound to one profile connection generation."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    connection_id: UUID
    generation: int
    changes: WorkspaceChanges = Field(repr=False)


class VerifiedReviewGrant(BaseModel):
    """Ephemeral host-only admission bindings; never includes source content."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    profile_id: UUID
    lease_hash: str = Field(repr=False, exclude=True)
    source_connection: UUID
    source_generation: int
    source_run: str
    source_hash: str
    post_run_hash: str
    patch_hash: str
    target_connection: UUID
    target_generation: int
    request_id: str
    instruction_hash: str
    request_body_hash: str | None = None
    expires_at: float
    graph_review: "GraphRunReview" = Field(repr=False)


class GraphRunNode(BaseModel):
    """One host-approved vertex and its exact saved-account generation."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    vertex_id: str = Field(min_length=1)
    provider: Literal["codex", "claude", "opencode"]
    connection_id: UUID
    generation: int = Field(ge=1)
    review_source: str | None = Field(default=None, min_length=1)
    policy: GraphNodePolicy | None = None


class GraphRunPlan(BaseModel):
    """Host-only approved graph identity, selections and absolute deadline."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    profile_id: UUID
    lease_hash: str = Field(min_length=1, repr=False, exclude=True)
    flow_id: UUID
    graph_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    nodes: tuple[GraphRunNode, ...]
    deadline: float


class GraphRunReview(BaseModel):
    """Host-derived source and target belonging to one live graph admission."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    profile_id: UUID
    lease_hash: str = Field(repr=False, exclude=True)
    worker_key: str = Field(repr=False, exclude=True)
    graph_digest: str
    source: GraphRunNode
    target: GraphRunNode
    source_run: str


class GraphNodeStart(BaseModel):
    """Host-generated request identity reserved before native model dispatch."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    node: GraphRunNode
    request_id: str


class GraphRunShutdown(BaseModel):
    """Revoked job's host request receipts, retained for cancellation/reconciliation."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    profile_id: UUID
    starts: tuple[GraphNodeStart, ...] = Field(repr=False, exclude=True)


class GraphNodeStop(BaseModel):
    """Native cancellation and task settlement are distinct host observations."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    connection_id: UUID
    generation: int
    run_id: str
    status: str
    cancel_confirmed: bool
    settled: bool


class StagedGraphReview(BaseModel):
    """Host-only native request and grant; workers receive only its expected hash."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    body: dict[str, JsonValue] = Field(repr=False, exclude=True)
    grant: str = Field(repr=False, exclude=True)
    expected_request_hash: str


class GraphReviewDispatch(BaseModel):
    """A fenced host request, provenance and graph binding for native reservation."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    body: dict[str, JsonValue] = Field(repr=False, exclude=True)
    provenance: VerifiedReviewProvenance
    graph_review: GraphRunReview = Field(repr=False, exclude=True)


class ConnectionRecord(BaseModel):
    """Host-only metadata committed after authenticated identity verification."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: Literal["codex", "claude", "opencode"] = Field(
        default="codex", description="Native harness owning this credential context."
    )
    connection_id: UUID = Field(
        description="Opaque local binding, never a token reference."
    )
    credential_id: UUID = Field(
        repr=False,
        description="Host-only immutable vault revision, separate from the local selector.",
    )
    client_id: str = Field(
        repr=False, description="Host-only SIWC client owning the credential."
    )
    subject_hash: str = Field(
        description="Verified issuer subject digest for duplicate admission."
    )
    generation: int = Field(
        ge=1,
        description="Stable connection_generation changed by reconnect, not token rotation.",
    )
    label: str = Field(
        max_length=100,
        description="Provider-verified display identity, not user proof.",
    )
    lifecycle: Literal["connected", "disconnecting", "cleanup_required"] = Field(
        default="connected",
        description="Durable local removal fence; only connected permits credential use.",
    )


class ConnectionIndex(BaseModel):
    """Private atomic admission index; unindexed credentials are not dispatchable."""

    model_config = ConfigDict(extra="forbid")
    connections: list[ConnectionRecord] = Field(
        default_factory=list, description="Profile-owned saved credential bindings."
    )


class ConnectionSummary(BaseModel):
    """Nonsecret profile-owned row; authentication does not certify inference."""

    connection_id: UUID = Field(description="Explicit local connection selector.")
    provider: Literal["codex", "claude", "opencode"] = Field(
        default="codex", description="Implemented provider integration."
    )
    method: Literal["chatgpt_plan_oauth", "claude_native", "opencode_go_key"] = Field(
        default="chatgpt_plan_oauth", description="Explicit ChatGPT plan route."
    )
    label: str = Field(description="Verified account display identity when available.")
    generation: int = Field(
        description="Observed stable connection_generation, independent of broker rotation."
    )
    auth_state: Literal[
        "ready", "expired", "reauthorization_required", "revoked", "unavailable"
    ] = Field(description="Credential observation only; runner state is independent.")
    lifecycle: Literal["connected", "disconnecting", "cleanup_required"] = Field(
        default="connected", description="Observed local removal and recovery phase."
    )


class DisconnectInfo(BaseModel):
    """Nonsecret confirmation snapshot; new admissions invalidate its revision."""

    connection_id: UUID = Field(description="Exact profile-owned connection to remove.")
    generation: int = Field(
        ge=1, description="Admitted connection generation to fence."
    )
    active_runs: int = Field(
        ge=0, description="Affected active runs and discovery operations."
    )
    revision: int = Field(
        ge=0, description="Controller admission revision for explicit confirmation."
    )


class SessionLeaseRenewal(BaseModel):
    """Opaque verified renewal evidence, retained only until token expiry."""

    model_config = ConfigDict(frozen=True)
    canonical_hash: str = Field(repr=False, description="Original revocation identity.")
    expires_at: float = Field(description="Verified cookie expiry as a Unix timestamp.")


class BrowserProviderSession(BaseModel):
    """Verified native browser principal and nonreusable request lease digest."""

    model_config = ConfigDict(frozen=True)
    profile_id: UUID = Field(
        description="Profile resolved by upstream native JWT verification."
    )
    flow_id: UUID | None = Field(
        default=None,
        description="Owned browser graph context for editor discovery only.",
    )
    lease_hash: str = Field(
        repr=False, description="Cookie digest for logout fencing; never a credential."
    )


class DisconnectRequest(BaseModel):
    """Explicit confirmation of the inspected connection and affected work."""

    model_config = ConfigDict(extra="forbid")
    generation: int = Field(
        ge=1, description="Previously inspected identity generation."
    )
    revision: int = Field(
        ge=0, description="Previously inspected controller admission revision."
    )


class DisconnectProgress(BaseModel):
    """Local removal outcome without claiming remote/provider account logout."""

    connection_id: UUID = Field(
        description="Connection whose local removal was requested."
    )
    status: Literal["disconnecting", "cleanup_required", "removed"] = Field(
        description="Removal is complete only after owned native and credential cleanup."
    )


class ControllerSlot(BaseModel):
    """Host-only inventory entry; never serialize runner objects or private paths."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    scope: Literal["graph", "assistant"] = Field(
        default="graph", description="Fixed host-owned execution workspace boundary."
    )
    profile_id: UUID = Field(description="Authenticated local owner.")
    connection_id: UUID = Field(description="Selected saved connection.")
    generation: int = Field(
        description="Identity epoch pinned to this runner and retained sessions."
    )
    state: Path = Field(
        exclude=True,
        repr=False,
        description="Private runtime state outside Git and tool mounts.",
    )
    runner: Any = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Trusted native Agent, absent while starting.",
    )
    server: Any = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Owned loopback gateway for existing graph protocol.",
    )
    creating: bool = Field(
        default=True, description="Startup/receipt reconciliation is still in flight."
    )
    operations: int = Field(
        default=0,
        description="Requests admitted before a disconnect fence and not yet returned.",
    )
    catalog_operations: int = Field(
        default=0,
        description="Native discovery requests currently borrowing this connection.",
    )
    revision: int = Field(
        default=0,
        description="Monotonic admission counter for disconnect confirmation.",
    )


class LoginProgress(BaseModel):
    """Bounded attempt receipt with no OAuth verifier, code or token material."""

    attempt_id: UUID = Field(
        description="Opaque attempt used for polling and explicit cancellation."
    )
    provider: Literal["codex", "claude"] = Field(
        default="codex",
        description="Native sign-in owner, independent of the browser's last selected tab.",
    )
    status: Literal[
        "connecting",
        "verifying",
        "connected",
        "cancelled",
        "expired",
        "failed",
        "duplicate",
    ] = Field(description="Attempt state; only connected admits a credential.")
    connection_id: UUID | None = Field(
        default=None, description="Admitted or duplicate saved connection, if known."
    )
    code: str | None = Field(
        default=None, description="Safe failure category, never raw provider text."
    )


class StartProviderLogin(BaseModel):
    """Explicit browser consent for the single implemented provider route."""

    model_config = ConfigDict(extra="forbid")
    provider: Literal["codex", "claude"] = Field(
        description="Chosen integration; unsupported types are refused."
    )
    connection_id: UUID | None = Field(
        default=None,
        description="Exact existing connection for reconnect, or a fresh candidate.",
    )


class SaveGoConnection(BaseModel):
    """Explicit Go subscription key admission; never included in a graph."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    key: SecretStr = Field(
        repr=False,
        description="Go subscription key submitted once over the local authenticated boundary.",
    )
    label: str = Field(
        min_length=1,
        max_length=100,
        description="User label; does not claim verified provider identity.",
    )


class SubmitClaudeCode(BaseModel):
    """A one-use code relayed only into the originating official native client."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    code: SecretStr = Field(
        repr=False,
        description="Official provider completion code; never persisted or logged.",
    )


class GraphProviderPreferences(BaseModel):
    """Local graph preference; no credentials or portable account binding."""

    model_config = ConfigDict(extra="forbid")
    codex: UUID | None = Field(
        default=None, description="Preferred Codex connection for this graph only."
    )
    claude: UUID | None = Field(
        default=None,
        description="Preferred Claude Code connection for this graph only.",
    )
    opencode: UUID | None = Field(
        default=None,
        description="Preferred OpenCode Go connection for this graph only.",
    )
