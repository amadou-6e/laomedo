"""Persisted connection identity and safe Settings projections."""

from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr
from laomedo.agents.agents.base.models import SubscriptionSnapshot


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


class SubscriptionBinding(BaseModel):
    """Immutable native-read key; browser leases gate visibility separately."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    profile_id: UUID = Field(
        description="Authenticated local profile owning the connection."
    )
    connection_id: UUID = Field(
        description="Exact saved account selector, never a credential path."
    )
    generation: int = Field(
        ge=1,
        description="Committed reconnect epoch; token rotation does not change it.",
    )


class SubscriptionRequest(BaseModel):
    """Explicit refresh of the account generation currently shown in the browser."""

    model_config = ConfigDict(strict=True, extra="forbid")
    generation: int = Field(
        ge=1,
        description="Expected saved connection generation shown by the account list.",
    )


class SubscriptionObservation(BaseModel):
    """Safe lease-visible account limits with explicit freshness and failure status."""

    model_config = ConfigDict(strict=True, extra="forbid")
    connection_id: UUID = Field(
        description="Saved account whose limits were requested."
    )
    generation: int = Field(
        ge=1, description="Exact reconnect epoch of this observation."
    )
    state: Literal["not_checked", "ready", "stale", "unavailable"] = Field(
        description="Observed availability; unavailable is never a zero balance."
    )
    reason: (
        Literal["unsupported", "refresh_failed", "account_unavailable", "busy"] | None
    ) = Field(
        default=None,
        description="Allowlisted recovery category, never a raw provider error.",
    )
    observed_at: float | None = Field(
        default=None,
        description="Unix seconds when a successful native observation finished teardown.",
    )
    stale_after: float | None = Field(
        default=None,
        description="Unix seconds after which this snapshot must be labelled out of date.",
    )
    snapshot: SubscriptionSnapshot | None = Field(
        default=None,
        description="Safe native quota values, absent until a successful account read.",
    )


class SubscriptionCacheEntry(BaseModel):
    """Internal bounded native observation; no token, raw response or host path."""

    model_config = ConfigDict(strict=True, extra="forbid")
    snapshot: SubscriptionSnapshot | None = Field(
        default=None,
        description="Most recent successful snapshot for one native binding.",
    )
    observed_at: float | None = Field(
        default=None,
        description="Successful native teardown timestamp in Unix seconds.",
    )
    stale_after: float | None = Field(
        default=None,
        description="Earliest freshness deadline, bounded by the next reported future reset.",
    )
    attempted_at: float = Field(
        description="Most recent refresh attempt, used to bound failed retries and retention."
    )
    reason: Literal["refresh_failed", "busy"] | None = Field(
        default=None,
        description="Safe latest refresh outcome; a previous snapshot is stale on failure.",
    )
