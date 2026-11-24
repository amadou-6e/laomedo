"""Bounded native plan quota discovery through the selected Claude login."""

from datetime import datetime
import hashlib
import json
import math
import unicodedata
from uuid import uuid4

from laomedo.agents.agents.base.models import SubscriptionBucket
from laomedo.agents.agents.base.models import SubscriptionSnapshot
from laomedo.agents.agents.base.models import SubscriptionWindow
from laomedo.agents.errors import RunnerError


class ClaudeSubscriptionQuota:
    """Read the pinned official client's experimental structured usage control."""

    def __init__(self, agent):
        """Bind the admitted provider; construction performs no native operation."""
        self.agent = agent

    def read(self) -> SubscriptionSnapshot:
        """Return plan evidence only after authentication and exact job cleanup."""
        self.agent._check_auth(timeout=15)
        initialize, usage = str(uuid4()), str(uuid4())
        requests = [
            {
                "type": "control_request",
                "request_id": initialize,
                "request": {"subtype": "initialize", "hooks": {}},
            },
            {
                "type": "control_request",
                "request_id": usage,
                "request": {"subtype": "get_usage", "skip_behaviors": True},
            },
        ]
        result = self.agent.container.control(
            [
                "--print",
                "--input-format",
                "stream-json",
                "--output-format",
                "stream-json",
                "--verbose",
                "--no-session-persistence",
                "--tools",
                "",
                "--restricted",
                "--setting-sources",
                "",
                "--strict-mcp-config",
                "--mcp-config",
                '{"mcpServers":{}}',
                "--permission-mode",
                "dontAsk",
                "--permission-prompts",
                "none",
            ],
            input=("\n".join(json.dumps(item) for item in requests) + "\n").encode(),
            timeout=45,
        )
        try:
            if result.exit_code or len(result.stdout) > 65536:
                raise ValueError()
            responses = {}
            for line in result.stdout.decode("utf-8").splitlines():
                event = json.loads(line)
                if (
                    not isinstance(event, dict)
                    or event.get("type") != "control_response"
                ):
                    raise ValueError()
                response = event["response"]
                request_id = response["request_id"]
                if (
                    response.get("subtype") != "success"
                    or request_id not in {initialize, usage}
                    or request_id in responses
                ):
                    raise ValueError()
                responses[request_id] = response.get("response")
            if set(responses) != {initialize, usage}:
                raise ValueError()
            snapshot = self.project(responses[usage])
        except (ValueError, KeyError, TypeError, AttributeError):
            raise RunnerError("provider_subscription_limits_unavailable") from None
        self.agent._prepare_credentials()
        return snapshot

    @classmethod
    def project(cls, payload) -> SubscriptionSnapshot:
        """Project bounded native plan windows; never infer missing allowance."""
        if (
            not isinstance(payload, dict)
            or payload.get("rate_limits_available") is not True
        ):
            raise ValueError("quota_unavailable")
        limits = payload.get("rate_limits")
        if not isinstance(limits, dict):
            raise ValueError("quota_unavailable")
        plan = payload.get("subscription_type")
        if plan is not None and (not isinstance(plan, str) or len(plan) > 64):
            raise ValueError("invalid_plan")
        windows = []
        for key, kind, minutes in (
            ("five_hour", "primary", 300),
            ("seven_day", "secondary", 10080),
        ):
            if limits.get(key) is not None:
                windows.append(cls._window(limits[key], kind, minutes))
        buckets = [
            SubscriptionBucket(
                limit_id="claude", label="Claude", plan=plan, windows=windows
            )
        ]
        for key, label in (
            ("seven_day_oauth_apps", "OAuth apps"),
            ("seven_day_opus", "Opus"),
            ("seven_day_sonnet", "Sonnet"),
        ):
            if limits.get(key) is not None:
                buckets.append(
                    SubscriptionBucket(
                        limit_id=key,
                        label=label,
                        plan=plan,
                        windows=[cls._window(limits[key], "secondary", 10080)],
                    )
                )
        scoped = limits.get("model_scoped", [])
        if not isinstance(scoped, list) or len(scoped) > 28:
            raise ValueError("invalid_scoped_windows")
        seen = set()
        for item in scoped:
            if not isinstance(item, dict):
                raise ValueError("invalid_scoped_window")
            label = item.get("display_name")
            if (
                not isinstance(label, str)
                or not label
                or len(label) > 128
                or any(unicodedata.category(c) in {"Cc", "Cf"} for c in label)
            ):
                raise ValueError("invalid_scoped_label")
            if label in seen:
                raise ValueError("duplicate_scoped_window")
            seen.add(label)
            buckets.append(
                SubscriptionBucket(
                    limit_id="model-" + hashlib.sha256(label.encode()).hexdigest(),
                    label=label,
                    plan=plan,
                    windows=[cls._window(item, "secondary", 10080)],
                )
            )
        return SubscriptionSnapshot(
            buckets=sorted(buckets, key=lambda item: item.limit_id)
        )

    @staticmethod
    def _window(value, kind, minutes) -> SubscriptionWindow:
        """Keep malformed scalar evidence unknown while refusing invalid structures."""
        if not isinstance(value, dict):
            raise ValueError("invalid_window")
        percent = value.get("utilization")
        try:
            valid_percent = (
                type(percent) in {int, float}
                and math.isfinite(percent)
                and percent >= 0
            )
        except OverflowError:
            valid_percent = False
        if not valid_percent:
            percent = None
        reset = None
        raw = value.get("resets_at")
        if isinstance(raw, str) and len(raw) <= 64:
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if parsed.tzinfo is not None:
                    timestamp = parsed.timestamp()
                    if 0 < timestamp <= 253402300799:
                        reset = int(timestamp)
            except (ValueError, OverflowError, OSError):
                pass
        return SubscriptionWindow(
            kind=kind, used_percent=percent, window_minutes=minutes, resets_at=reset
        )
