"""Bounded Go usage observations through the execution connection's private key."""

from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from laomedo.agents.agents.base.models import SubscriptionBucket
from laomedo.agents.agents.base.models import SubscriptionSnapshot
from laomedo.agents.agents.base.models import SubscriptionWindow
from laomedo.agents.agents.opencode.settings import GO_USAGE_MAX_BYTES
from laomedo.agents.agents.opencode.settings import GO_USAGE_TIMEOUT_SECONDS
from laomedo.agents.agents.opencode.settings import GO_USAGE_URL
from laomedo.agents.agents.opencode.utils import check_auth_fresh
from laomedo.agents.errors import RunnerError


class GoUsageRedirectHandler(HTTPRedirectHandler):
    """Refuse redirects so the saved key is sent only to the fixed Go endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Let urllib produce a bounded failure without following another address."""
        return None


class OpenCodeSubscriptionQuota:
    """Read one admitted Go profile without inference or credential modification."""

    def __init__(self, profile):
        """Bind an existing provider-owned credential directory without reading it."""
        self.profile = Path(profile)

    def read(self) -> SubscriptionSnapshot:
        """Return safe meters after custody revalidation; never retain raw errors."""
        try:
            check_auth_fresh(self.profile)
            key = json.loads((self.profile / "auth.json").read_text(encoding="utf-8"))[
                "opencode-go"
            ]["key"]
            if not isinstance(key, str) or not key or any(c in key for c in "\r\n"):
                raise ValueError()
            fingerprint = hashlib.sha256(key.encode()).hexdigest()
            request = Request(
                GO_USAGE_URL,
                headers={
                    "Authorization": "Bearer " + key,
                    "Accept": "application/json",
                },
                method="GET",
            )
            # Ignore ambient proxy configuration; no other host receives this key.
            opener = build_opener(ProxyHandler({}), GoUsageRedirectHandler())
            with opener.open(request, timeout=GO_USAGE_TIMEOUT_SECONDS) as response:
                if response.status != 200:
                    raise ValueError()
                payload = response.read(GO_USAGE_MAX_BYTES + 1)
            if len(payload) > GO_USAGE_MAX_BYTES:
                raise ValueError()
            snapshot = self.project(json.loads(payload))
            check_auth_fresh(self.profile)
            current = json.loads(
                (self.profile / "auth.json").read_text(encoding="utf-8")
            )["opencode-go"]["key"]
            if hashlib.sha256(current.encode()).hexdigest() != fingerprint:
                raise ValueError()
            return snapshot
        except HTTPError as error:
            status = error.code
            error.close()
            code = {
                401: "opencode_go_usage_authentication_failed",
                403: "opencode_go_usage_not_entitled",
                429: "opencode_go_usage_rate_limited",
            }.get(status, "provider_subscription_limits_unavailable")
            raise RunnerError(code) from None
        except (
            RunnerError,
            OSError,
            URLError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
        ):
            raise RunnerError("provider_subscription_limits_unavailable") from None

    @classmethod
    def project(cls, payload) -> SubscriptionSnapshot:
        """Preserve every documented meter, without inventing missing scalar values."""
        if not isinstance(payload, dict) or not isinstance(payload.get("usage"), dict):
            raise ValueError("usage_unavailable")
        windows = []
        for name, kind, minutes in (
            ("rolling", "primary", 300),
            ("weekly", "secondary", 10080),
            ("monthly", "monthly", None),
        ):
            meter = payload["usage"].get(name)
            if meter is None:
                continue
            if not isinstance(meter, dict) or meter.get("status") not in {
                "ok",
                "rate-limited",
            }:
                raise ValueError("usage_invalid")
            percent = meter.get("percent")
            if (
                isinstance(percent, bool)
                or not isinstance(percent, (int, float))
                or not math.isfinite(percent)
                or not 0 <= percent <= 100
            ):
                percent = None
            windows.append(
                SubscriptionWindow(
                    kind=kind,
                    used_percent=float(percent) if percent is not None else None,
                    window_minutes=minutes,
                    resets_at=cls._reset(meter.get("resetsAt")),
                )
            )
        return SubscriptionSnapshot(
            buckets=[
                SubscriptionBucket(
                    limit_id="opencode-go", label="OpenCode Go", windows=windows
                )
            ]
        )

    @staticmethod
    def _reset(value):
        """Accept only an explicit timezone-bearing reset within the wire range."""
        if not isinstance(value, str) or len(value) > 64:
            return None
        try:
            reset = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if reset.tzinfo is None:
                return None
            timestamp = int(reset.timestamp())
            return timestamp if 0 < timestamp <= 253402300799 else None
        except (ValueError, OverflowError, OSError):
            return None
