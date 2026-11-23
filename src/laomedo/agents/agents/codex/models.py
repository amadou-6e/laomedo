"""Codex-owned continuation bindings, separate from successful output artifacts."""

from pydantic import BaseModel, ConfigDict, Field
from pathlib import Path
from uuid import UUID
from typing import Any
from pydantic import SecretStr
from laomedo.agents.connections.models import ConnectionRecord, LoginProgress


class ResumeCheckpoint(BaseModel):
    """Bind a settled interrupted attempt to its existing session and frozen files."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    attempt_id: str = Field(
        description="Exact settled Activity attempt that owns these facts."
    )
    thread_id: str = Field(
        description="Existing native session; no fresh-session substitution."
    )
    workspace_hash: str = Field(
        pattern=r"^sha256:[0-9a-f]{64}$",
        description="Verified retained workspace digest after owned resources settled.",
    )
    runner_instance_id: str = Field(
        description="Only this still-running host can admit continuation."
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


class IdleCodexSession(BaseModel):
    """Process-local native session retained before any model turn materializes it."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")
    closing: bool = Field(
        default=False,
        exclude=True,
        description="Cleanup has begun; this runtime cannot be taken for another message.",
    )
    runtime: Any = Field(
        exclude=True,
        repr=False,
        description="Exact live native runtime on its original event loop.",
    )
    lease: Any = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Existing independent resource lease, when configured.",
    )
    cancelled: Any = Field(
        exclude=True,
        repr=False,
        description="Original cancellation event also observed by its resource lease.",
    )
    ownership: dict = Field(
        exclude=True,
        repr=False,
        description="Exact recorded Docker ownership; never a replacement identity.",
    )
    credential_digest: str | None = Field(
        default=None,
        exclude=True,
        repr=False,
        description="In-memory last admitted bearer digest for refresh detection; never serialized.",
    )
    expires: float = Field(
        exclude=True, description="Monotonic deadline for an unused live session."
    )
