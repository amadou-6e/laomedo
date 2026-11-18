"""Current zero-turn quota projection and native extension contracts."""

import asyncio
import unittest
from unittest.mock import AsyncMock, Mock

from laomedo.agents.agents.codex.models import CodexRateLimits
from laomedo.agents.agents.codex.runtime import CodexAgentRuntime
from laomedo.agents.errors import RunnerError


class SubscriptionLimitTests(unittest.TestCase):
    """Protect native bucket semantics without manufacturing integration acceptance."""

    def test_multi_bucket_is_authoritative_and_sorted(self):
        result = CodexRateLimits.model_validate(
            {
                "rateLimits": {"primary": {"usedPercent": 99}},
                "rateLimitsByLimitId": {
                    "review": {
                        "limitName": "Review",
                        "secondary": {
                            "usedPercent": 110,
                            "windowDurationMins": 10080,
                            "resetsAt": 1900000000,
                        },
                    },
                    "codex": {
                        "primary": {"usedPercent": 25.5, "windowDurationMins": 300}
                    },
                },
            }
        ).to_snapshot()
        self.assertEqual([b.limit_id for b in result.buckets], ["codex", "review"])
        self.assertEqual(result.buckets[0].windows[0].used_percent, 25.5)
        self.assertEqual(result.buckets[1].windows[0].kind, "secondary")
        self.assertEqual(result.buckets[1].windows[0].used_percent, 110)
        self.assertEqual(result.submitted_turns, 0)

    def test_empty_authoritative_map_does_not_restore_fallback(self):
        result = CodexRateLimits.model_validate(
            {"rateLimits": {"primary": {"usedPercent": 40}}, "rateLimitsByLimitId": {}}
        ).to_snapshot()
        self.assertEqual(result.buckets, [])

    def test_fallback_preserves_missing_windows_and_credit_evidence(self):
        result = CodexRateLimits.model_validate(
            {
                "rateLimits": {
                    "limitId": "codex",
                    "primary": None,
                    "secondary": {"usedPercent": 0},
                    "credits": {
                        "hasCredits": True,
                        "unlimited": False,
                        "balance": "10.25",
                        "privateToken": "not-forwarded",
                    },
                }
            }
        ).to_snapshot()
        bucket = result.buckets[0]
        self.assertEqual(len(bucket.windows), 1)
        self.assertEqual(bucket.windows[0].used_percent, 0)
        self.assertIsNone(bucket.windows[0].resets_at)
        self.assertEqual(bucket.credits.balance, "10.25")
        self.assertNotIn("privateToken", str(result.model_dump()))

    def test_invalid_scalar_only_removes_that_observation(self):
        for value in [-1, float("nan"), float("inf"), "20", True, None]:
            with self.subTest(value=value):
                result = CodexRateLimits.model_validate(
                    {
                        "rateLimits": {
                            "primary": {
                                "usedPercent": value,
                                "windowDurationMins": 300,
                                "resetsAt": 1.5,
                            }
                        }
                    }
                ).to_snapshot()
                window = result.buckets[0].windows[0]
                self.assertIsNone(window.used_percent)
                self.assertIsNone(window.resets_at)
                self.assertEqual(window.window_minutes, 300)

    def test_bad_structure_and_bounds_fail_without_partial_snapshot(self):
        for response in [
            {"rateLimits": []},
            {"rateLimits": {"primary": []}},
            {"rateLimitsByLimitId": {"a": []}},
            {"rateLimitsByLimitId": {str(i): {} for i in range(33)}},
            {"rateLimits": {"limitName": "x" * 129}},
        ]:
            with self.subTest(response=response), self.assertRaises(ValueError):
                CodexRateLimits.model_validate(response).to_snapshot()

    def test_native_request_is_named_and_empty(self):
        server = Mock(
            extension=AsyncMock(
                return_value={"rateLimits": {"primary": {"usedPercent": 25}}}
            )
        )
        result = asyncio.run(CodexAgentRuntime.subscription_limits(server))
        server.extension.assert_awaited_once_with("laomedo/codexRateLimits", {})
        self.assertEqual(result.submitted_turns, 0)
        self.assertEqual(result.buckets[0].windows[0].used_percent, 25)

    def test_unbounded_or_malformed_native_response_fails_safely(self):
        for response in [[], {"raw": "x" * 65536}, {"rateLimits": {"credits": []}}]:
            with self.subTest(response=type(response).__name__):
                server = Mock(extension=AsyncMock(return_value=response))
                with self.assertRaisesRegex(RunnerError, "runner_transport_failed"):
                    asyncio.run(CodexAgentRuntime.subscription_limits(server))
