"""Bounded Go usage observations through the execution connection's private key."""

from datetime import datetime
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path

from laomedo.agents.agents.base.models import SubscriptionBucket
from laomedo.agents.agents.base.models import SubscriptionSnapshot
from laomedo.agents.agents.base.models import SubscriptionWindow
from laomedo.agents.agents.opencode.settings import GO_USAGE_MAX_BYTES
from laomedo.agents.agents.opencode.settings import GO_USAGE_TIMEOUT_SECONDS
from laomedo.agents.agents.opencode.settings import GO_USAGE_URL
from laomedo.agents.agents.opencode.utils import check_auth_fresh
from laomedo.agents.errors import RunnerError


class OpenCodeSubscriptionQuota:
    """Read one admitted Go profile without inference or credential modification."""

    # Isolated standard-library HTTP reader. The key crosses stdin only, never
    # argv/environment. Process timeout bounds DNS, headers and slow bodies too.
    _HTTP_READER = r"""
import sys
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None
try:
    key = sys.stdin.buffer.read(8193).decode('utf-8')
    if not key or len(key.encode()) > 8192 or '\r' in key or '\n' in key:
        sys.exit(1)
    request = Request(sys.argv[1], headers={'Authorization': 'Bearer ' + key, 'Accept': 'application/json'}, method='GET')
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=float(sys.argv[3])) as response:
        if response.status != 200:
            sys.exit(1)
        body = response.read(int(sys.argv[2]) + 1)
    if len(body) > int(sys.argv[2]):
        sys.exit(1)
    sys.stdout.buffer.write(body)
except HTTPError as error:
    status = error.code
    error.close()
    sys.exit({401: 11, 403: 13, 429: 29}.get(status, 1))
except Exception:
    sys.exit(1)
"""

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
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    "-c",
                    self._HTTP_READER,
                    GO_USAGE_URL,
                    str(GO_USAGE_MAX_BYTES),
                    str(GO_USAGE_TIMEOUT_SECONDS),
                ],
                input=key.encode(),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=GO_USAGE_TIMEOUT_SECONDS,
                env={
                    name: os.environ[name]
                    for name in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP")
                    if name in os.environ
                },
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
            if result.returncode:
                raise RunnerError(
                    {
                        11: "opencode_go_usage_authentication_failed",
                        13: "opencode_go_usage_not_entitled",
                        29: "opencode_go_usage_rate_limited",
                    }.get(result.returncode, "provider_subscription_limits_unavailable")
                )
            payload = result.stdout
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
        except RunnerError as error:
            code = (
                error.code
                if error.code
                in {
                    "opencode_go_usage_authentication_failed",
                    "opencode_go_usage_not_entitled",
                    "opencode_go_usage_rate_limited",
                }
                else "provider_subscription_limits_unavailable"
            )
            raise RunnerError(code) from None
        except (
            OSError,
            subprocess.SubprocessError,
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
            raise ValueError()
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
                raise ValueError()
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
