"""Current Go usage protocol, credential custody and bounded HTTP regressions."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import Mock, patch

from laomedo.agents.agents.opencode.quota import OpenCodeSubscriptionQuota
from laomedo.agents.agents.opencode.settings import GO_USAGE_MAX_BYTES
from laomedo.agents.agents.opencode.settings import GO_USAGE_URL
from laomedo.agents.errors import RunnerError


class GoUsageHandler(BaseHTTPRequestHandler):
    """Local controlled HTTP boundary; no real subscription or authentication claim."""

    def do_GET(self):
        self.server.observed.append(
            (self.command, self.path, self.headers.get("Authorization"))
        )
        self.send_response(self.server.status)
        self.send_header("Location", "/must-not-follow")
        self.end_headers()
        try:
            if self.server.slow:
                for byte in self.server.body:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                    time.sleep(0.05)
            else:
                self.wfile.write(self.server.body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def log_message(self, *args):
        """Keep test-only bearer material out of server logs."""


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

    def start_server(self, status=200, body=None, *, slow=False):
        server = HTTPServer(("127.0.0.1", 0), GoUsageHandler)
        server.status = status
        server.body = json.dumps(self.payload).encode() if body is None else body
        server.slow = slow
        server.observed = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)
        endpoint = f"http://127.0.0.1:{server.server_port}/usage"
        patcher = patch("laomedo.agents.agents.opencode.quota.GO_USAGE_URL", endpoint)
        patcher.start()
        self.addCleanup(patcher.stop)
        return server

    def test_get_uses_saved_key_without_inference_or_redirects(self):
        server = self.start_server()
        result = self.quota.read()
        self.assertEqual(result.submitted_turns, 0)
        self.assertEqual(server.observed, [("GET", "/usage", "Bearer " + self.key)])

    def test_redirect_never_forwards_the_key(self):
        server = self.start_server(302)
        with self.assertRaises(RunnerError) as caught:
            self.quota.read()
        self.assertEqual(
            caught.exception.code, "provider_subscription_limits_unavailable"
        )
        self.assertEqual(len(server.observed), 1)
        self.assertEqual(server.observed[0][1], "/usage")

    def test_safe_http_categories_discard_upstream_body(self):
        for status, code in (
            (401, "opencode_go_usage_authentication_failed"),
            (403, "opencode_go_usage_not_entitled"),
            (429, "opencode_go_usage_rate_limited"),
            (503, "provider_subscription_limits_unavailable"),
        ):
            server = self.start_server(status, self.key.encode())
            with self.subTest(status=status), self.assertRaises(RunnerError) as caught:
                self.quota.read()
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn(self.key, str(caught.exception))
            self.assertEqual(len(server.observed), 1)

    def test_oversize_and_protocol_errors_are_sanitized(self):
        for body in (b"x" * (GO_USAGE_MAX_BYTES + 1), b"not json", b"[]"):
            self.start_server(body=body)
            with self.subTest(size=len(body)), self.assertRaises(RunnerError) as caught:
                self.quota.read()
            self.assertEqual(
                caught.exception.code, "provider_subscription_limits_unavailable"
            )

    def test_hard_deadline_kills_and_joins_slow_body_reader(self):
        self.start_server(body=b"x" * 20, slow=True)
        started = time.monotonic()
        with patch(
            "laomedo.agents.agents.opencode.quota.GO_USAGE_TIMEOUT_SECONDS", 0.2
        ):
            with self.assertRaises(RunnerError) as caught:
                self.quota.read()
        self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(
            caught.exception.code, "provider_subscription_limits_unavailable"
        )

    def test_child_arguments_and_environment_never_contain_key(self):
        result = subprocess.CompletedProcess([], 0, json.dumps(self.payload).encode())
        with patch(
            "laomedo.agents.agents.opencode.quota.subprocess.run", return_value=result
        ) as run:
            self.quota.read()
        args, options = run.call_args.args[0], run.call_args.kwargs
        self.assertEqual(options["input"], self.key.encode())
        self.assertNotIn(self.key, str(args))
        self.assertIn("-I", args)
        self.assertEqual(options["timeout"], 15)
        self.assertEqual(options["stderr"], subprocess.DEVNULL)
        self.assertLessEqual(
            set(options["env"]), {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
        )

    def test_key_changed_during_read_cannot_publish_snapshot(self):
        def rotate(*args, **kwargs):
            self.save_key("replacement-test-key")
            return subprocess.CompletedProcess([], 0, json.dumps(self.payload).encode())

        with patch(
            "laomedo.agents.agents.opencode.quota.subprocess.run", side_effect=rotate
        ):
            with self.assertRaises(RunnerError):
                self.quota.read()

    def test_invalid_local_custody_never_starts_reader(self):
        (self.profile / "auth-validity.json").unlink()
        with patch("laomedo.agents.agents.opencode.quota.subprocess.run") as run:
            with self.assertRaises(RunnerError):
                self.quota.read()
            run.assert_not_called()
