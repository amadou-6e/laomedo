"""Current Go usage protocol, credential custody and bounded HTTP regressions."""

import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from laomedo.agents.agents.opencode.quota import GoUsageRedirectHandler
from laomedo.agents.agents.opencode.quota import OpenCodeSubscriptionQuota
from laomedo.agents.agents.opencode.settings import GO_USAGE_MAX_BYTES
from laomedo.agents.agents.opencode.settings import GO_USAGE_URL
from laomedo.agents.errors import RunnerError


class GoQuotaTests(unittest.TestCase):
    """Exercise actual projection and custody with a controlled HTTP boundary."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.profile = Path(self.temporary.name)
        self.key = "test-only-go-key"
        self.save_key(self.key)
        self.payload = {
            "usage": {
                name: {
                    "status": "ok",
                    "percent": percent,
                    "resetsAt": "2026-12-01T00:00:00.000Z",
                }
                for name, percent in (("rolling", 30), ("weekly", 100), ("monthly", 50))
            }
        }
        self.quota = OpenCodeSubscriptionQuota(self.profile)

    def save_key(self, key):
        (self.profile / "auth.json").write_text(
            json.dumps({"opencode-go": {"type": "api", "key": key}})
        )
        (self.profile / "auth-validity.json").write_text(
            json.dumps(
                {
                    "credential_sha256": hashlib.sha256(key.encode()).hexdigest(),
                    "credential_mode": "provider_key",
                    "expires_at_ms": None,
                }
            )
        )

    def response(self, body=None):
        response = Mock(status=200)
        response.read.return_value = (
            json.dumps(self.payload).encode() if body is None else body
        )
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def test_preserves_three_meters_without_assuming_month_duration(self):
        self.payload["usage"]["weekly"]["status"] = "rate-limited"
        result = self.quota.project(self.payload)
        self.assertEqual(result.submitted_turns, 0)
        windows = result.buckets[0].windows
        self.assertEqual([w.kind for w in windows], ["primary", "secondary", "monthly"])
        self.assertEqual([w.window_minutes for w in windows], [300, 10080, None])
        self.assertEqual([w.used_percent for w in windows], [30, 100, 50])
        self.assertEqual(windows[2].resets_at, 1796083200)

    def test_unknown_scalar_and_absent_meter_never_become_zero(self):
        self.payload["usage"].pop("weekly")
        for percent in (None, True, -1, 101, "50", float("nan")):
            with self.subTest(percent=percent):
                self.payload["usage"]["rolling"]["percent"] = percent
                self.payload["usage"]["rolling"]["resetsAt"] = "2026-12-01T00:00:00"
                windows = self.quota.project(self.payload).buckets[0].windows
                self.assertEqual(len(windows), 2)
                self.assertIsNone(windows[0].used_percent)
                self.assertIsNone(windows[0].resets_at)

    def test_invalid_structure_is_refused(self):
        for payload in (
            None,
            [],
            {},
            {"usage": []},
            {"usage": {"monthly": []}},
            {"usage": {"monthly": {"status": "unknown"}}},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.quota.project(payload)

    def test_get_uses_only_saved_key_fixed_endpoint_and_bounded_read(self):
        response = self.response()
        with patch("laomedo.agents.agents.opencode.quota.build_opener") as build:
            build.return_value.open.return_value = response
            result = self.quota.read()
        request = build.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, GO_USAGE_URL)
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + self.key)
        self.assertIsNone(request.data)
        self.assertEqual(build.return_value.open.call_args.kwargs, {"timeout": 15})
        response.read.assert_called_once_with(GO_USAGE_MAX_BYTES + 1)
        response.__exit__.assert_called_once()
        self.assertEqual(result.submitted_turns, 0)
        self.assertTrue(
            any(
                isinstance(handler, GoUsageRedirectHandler)
                for handler in build.call_args.args
            )
        )

    def test_redirect_handler_never_forwards_credentials(self):
        self.assertIsNone(
            GoUsageRedirectHandler().redirect_request(
                None, None, 302, "redirect", {}, "https://other.example"
            )
        )

    def test_safe_http_categories_never_include_upstream_body_or_key(self):
        for status, code in (
            (401, "opencode_go_usage_authentication_failed"),
            (403, "opencode_go_usage_not_entitled"),
            (429, "opencode_go_usage_rate_limited"),
            (302, "provider_subscription_limits_unavailable"),
            (503, "provider_subscription_limits_unavailable"),
        ):
            body = io.BytesIO(self.key.encode())
            error = HTTPError(GO_USAGE_URL, status, self.key, {}, body)
            with (
                self.subTest(status=status),
                patch("laomedo.agents.agents.opencode.quota.build_opener") as build,
            ):
                build.return_value.open.side_effect = error
                with self.assertRaises(RunnerError) as caught:
                    self.quota.read()
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn(self.key, str(caught.exception))
                self.assertTrue(body.closed)

    def test_transport_oversize_and_protocol_errors_are_sanitized(self):
        for failure in (
            URLError(self.key),
            b"x" * (GO_USAGE_MAX_BYTES + 1),
            b"not json",
            b"[]",
        ):
            with (
                self.subTest(failure=type(failure).__name__),
                patch("laomedo.agents.agents.opencode.quota.build_opener") as build,
            ):
                if isinstance(failure, Exception):
                    build.return_value.open.side_effect = failure
                else:
                    build.return_value.open.return_value = self.response(failure)
                with self.assertRaises(RunnerError) as caught:
                    self.quota.read()
                self.assertEqual(
                    caught.exception.code, "provider_subscription_limits_unavailable"
                )
                self.assertNotIn(self.key, str(caught.exception))

    def test_key_changed_during_read_cannot_publish_snapshot(self):
        response = self.response()

        def rotate(limit):
            self.save_key("replacement-test-key")
            return json.dumps(self.payload).encode()

        response.read.side_effect = rotate
        with patch("laomedo.agents.agents.opencode.quota.build_opener") as build:
            build.return_value.open.return_value = response
            with self.assertRaises(RunnerError):
                self.quota.read()

    def test_invalid_local_custody_never_sends_request(self):
        (self.profile / "auth-validity.json").unlink()
        with patch("laomedo.agents.agents.opencode.quota.build_opener") as build:
            with self.assertRaises(RunnerError):
                self.quota.read()
            build.assert_not_called()
