"""Codex-owned continuation bindings, separate from successful output artifacts."""

from pydantic import JsonValue
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


class CodexRateLimits(BaseModel):
    """Bound the native rate-limit response and project only safe explicit fields."""

    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)
    rateLimits: dict[str, JsonValue] | None = Field(
        default=None,
        repr=False,
        description="Legacy single-bucket native view, used only when the multi-bucket view is absent.",
    )
    rateLimitsByLimitId: dict[str, dict[str, JsonValue]] | None = Field(
        default=None,
        repr=False,
        description="Authoritative native metered buckets keyed by ID, including an empty reported map.",
    )

    def to_snapshot(self):
        """Normalize bounded native evidence; invalid scalar fields become unknown, invalid shapes fail."""
        import math
        import re
        from laomedo.agents.agents.base.models import SubscriptionBucket
        from laomedo.agents.agents.base.models import SubscriptionCredits
        from laomedo.agents.agents.base.models import SubscriptionSnapshot
        from laomedo.agents.agents.base.models import SubscriptionWindow

        native = self.rateLimitsByLimitId
        if native is None:
            if self.rateLimits is None:
                native = {}
            else:
                identity = self.rateLimits.get("limitId") or "codex"
                if not isinstance(identity, str):
                    raise ValueError("subscription_response_invalid")
                native = {identity: self.rateLimits}
        if len(native) > 32:
            raise ValueError("subscription_response_invalid")
        buckets = []
        for identity, raw in sorted(native.items()):
            windows = []
            for kind in ("primary", "secondary"):
                value = raw.get(kind)
                if value is None:
                    continue
                if not isinstance(value, dict):
                    raise ValueError("subscription_response_invalid")
                used = value.get("usedPercent")
                try:
                    used = (
                        float(used)
                        if type(used) in (int, float)
                        and math.isfinite(used)
                        and used >= 0
                        else None
                    )
                except OverflowError:
                    used = None
                minutes = value.get("windowDurationMins")
                minutes = (
                    minutes
                    if type(minutes) is int and 0 < minutes <= 52560000
                    else None
                )
                reset = value.get("resetsAt")
                reset = (
                    reset if type(reset) is int and 0 < reset <= 253402300799 else None
                )
                windows.append(
                    SubscriptionWindow(
                        kind=kind,
                        used_percent=used,
                        window_minutes=minutes,
                        resets_at=reset,
                    )
                )
            credits = None
            value = raw.get("credits")
            if value is not None:
                if not isinstance(value, dict):
                    raise ValueError("subscription_response_invalid")
                balance = value.get("balance")
                balance = (
                    balance
                    if isinstance(balance, str)
                    and len(balance) <= 64
                    and re.fullmatch(r"-?[0-9]+(?:[.][0-9]+)?", balance)
                    else None
                )
                credits = SubscriptionCredits(
                    has_credits=(
                        value.get("hasCredits")
                        if type(value.get("hasCredits")) is bool
                        else None
                    ),
                    unlimited=(
                        value.get("unlimited")
                        if type(value.get("unlimited")) is bool
                        else None
                    ),
                    balance=balance,
                )
            buckets.append(
                SubscriptionBucket(
                    limit_id=identity,
                    label=raw.get("limitName"),
                    plan=raw.get("planType"),
                    windows=windows,
                    credits=credits,
                )
            )
        return SubscriptionSnapshot(buckets=buckets)


class CodexNativeProfile(BaseModel):
    """Host-owned native volume, pinned to its original daemon and immutable image."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    name: str = Field(pattern=r"^laomedo-codex-connection-[0-9a-f]{32}$")
    labels: dict[str, str] = Field(
        repr=False, description="Exact SDK ownership labels."
    )
    docker_endpoint: str = Field(min_length=1, repr=False)
    image_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class CodexAccountIdentity(BaseModel):
    """Public native observations; email changes require explicit replacement."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )
    email: str = Field(min_length=1, max_length=100)
    account_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    plan_type: str = Field(min_length=1, max_length=64)

    def subject_hash(self) -> str:
        """Bind observed native account/workspace and email, without token claims."""
        import hashlib
        import json

        return hashlib.sha256(
            json.dumps(
                {"email": self.email.casefold(), "account_id": self.account_id},
                sort_keys=True,
            ).encode()
        ).hexdigest()


class CodexLoginAttempt(BaseModel):
    """Process-local native login; every live handle and URL is excluded."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    profile_id: UUID = Field(
        exclude=True, description="Authenticated local profile owning the attempt."
    )
    lease_hash: str = Field(
        exclude=True,
        repr=False,
        description="Originating browser lease, fenced on logout.",
    )
    candidate_id: UUID = Field(
        exclude=True, description="New or reconnecting saved connection."
    )
    credential_id: UUID = Field(
        exclude=True, description="Fresh immutable native volume revision."
    )
    previous: ConnectionRecord | None = Field(
        default=None,
        exclude=True,
        description="Committed connection preserved until successful replacement.",
    )
    expires_at: float = Field(
        exclude=True, description="Monotonic native attempt expiry."
    )
    progress: LoginProgress = Field(description="Safe observable attempt state.")
    authorization_url: SecretStr | None = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Official-client URL, only relayed to the owning browser.",
    )
    session: Any = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Live creator-owned native stdin session.",
    )
    cancelled: Any = Field(
        exclude=True,
        repr=False,
        description="Cancellation event observed by the native lifecycle.",
    )
    ready: Any = Field(
        exclude=True,
        repr=False,
        description="Event announcing a URL or a terminal failure.",
    )
    worker: Any = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Owning worker; joined before final store closure.",
    )
    settled: bool = Field(
        default=False,
        exclude=True,
        description="Whether native session cleanup and publication have settled.",
    )

    user_code: SecretStr | None = Field(default=None, exclude=True, repr=False)
    identity: CodexAccountIdentity | None = Field(default=None, exclude=True)
    confirmation: Any = Field(
        exclude=True, repr=False, description="Explicit replacement confirmation event."
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
