"""Codex-owned continuation bindings, separate from successful output artifacts."""

from pydantic import JsonValue
from pydantic import BaseModel, ConfigDict, Field


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
                used = (
                    float(used)
                    if type(used) in (int, float) and math.isfinite(used) and used >= 0
                    else None
                )
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
