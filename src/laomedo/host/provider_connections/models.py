"""Persisted connection identity and safe Settings projections."""

from typing import Any, Literal
from uuid import UUID
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ConnectionRecord(BaseModel):
    """Host-only metadata committed after authenticated identity verification."""

    model_config = ConfigDict(extra="forbid", frozen=True)
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
    provider: Literal["codex"] = Field(
        default="codex", description="Implemented provider integration."
    )
    method: Literal["chatgpt_plan_oauth"] = Field(
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


class BrowserProviderSession(BaseModel):
    """Verified native browser principal and nonreusable request lease digest."""

    model_config = ConfigDict(frozen=True)
    profile_id: UUID = Field(
        description="Profile resolved by upstream native JWT verification."
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
    provider: Literal["codex"] = Field(
        description="Chosen integration; unsupported types are refused."
    )
    connection_id: UUID | None = Field(
        default=None,
        description="Exact existing connection for reconnect, or a fresh candidate.",
    )


class PendingLogin(BaseModel):
    """Process-local attempt secret, never serialized to Settings or persisted."""

    model_config = ConfigDict(extra="forbid")
    exchanging: bool = Field(
        default=False,
        exclude=True,
        description="Native exchange/cleanup is in flight even if its receipt was fenced.",
    )
    profile_id: UUID = Field(
        exclude=True, description="Authenticated profile owning the attempt."
    )
    lease_hash: str = Field(
        exclude=True,
        repr=False,
        description="Digest of the originating browser session, fenced on logout.",
    )
    candidate_id: UUID = Field(
        exclude=True, description="Proposed or reconnecting connection."
    )
    oauth: SecretStr = Field(
        exclude=True, description="Serialized private PKCE and nonce state."
    )
    stage: Path = Field(
        exclude=True,
        repr=False,
        description="Private unadmitted token staging directory.",
    )
    expires_at: float = Field(
        exclude=True, description="Monotonic expiry for this process only."
    )
    previous: ConnectionRecord | None = Field(
        default=None,
        exclude=True,
        description="Exact prior generation for reconnect admission.",
    )
    publication: ConnectionRecord | None = Field(
        default=None,
        exclude=True,
        description="Proposed admission pointer retained for uncertain-write reconciliation.",
    )
    superseded_scrubbed: bool = Field(
        default=False,
        exclude=True,
        description="Whether this attempt's prior local token copy has been removed.",
    )
    progress: LoginProgress = Field(
        description="Safe observation of the attempt lifecycle."
    )


class GraphProviderPreferences(BaseModel):
    """Local graph preference; no credentials or portable account binding."""

    model_config = ConfigDict(extra="forbid")
    codex: UUID | None = Field(
        default=None, description="Preferred Codex connection for this graph only."
    )
