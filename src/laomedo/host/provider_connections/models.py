"""Persisted connection identity and safe Settings projections."""

from typing import Literal
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
    progress: LoginProgress = Field(
        description="Safe observation of the attempt lifecycle."
    )
