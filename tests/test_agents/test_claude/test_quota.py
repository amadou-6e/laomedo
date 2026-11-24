"""Current Claude quota projection and zero-turn control protocol invariants."""

import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

from laomedo.agents.agents.claude.quota import ClaudeSubscriptionQuota
from laomedo.agents.errors import RunnerError


class ClaudeQuotaTests(TestCase):
    def setUp(self):
        self.agent = Mock()
        self.reader = ClaudeSubscriptionQuota(self.agent)
        self.payload = {
            "rate_limits_available": True,
            "subscription_type": "max",
            "rate_limits": {
                "five_hour": {"utilization": 100, "resets_at": "2030-01-01T12:00:00Z"},
                "seven_day": {"utilization": 42, "resets_at": None},
            },
        }

    def transport(self, args, *, input, timeout):
        sent = [json.loads(line) for line in input.splitlines()]
        self.assertEqual([item["type"] for item in sent], ["control_request"] * 2)
        self.assertEqual(sent[0]["request"], {"subtype": "initialize", "hooks": {}})
        self.assertEqual(
            sent[1]["request"], {"subtype": "get_usage", "skip_behaviors": True}
        )
        self.assertIn("--no-session-persistence", args)
        self.assertIn("--restricted", args)
        self.assertNotIn("--model", args)
        self.assertEqual(timeout, 45)
        responses = [
            {
                "type": "control_response",
                "response": {
                    "subtype": "success",
                    "request_id": item["request_id"],
                    "response": {} if index == 0 else self.payload,
                },
            }
            for index, item in enumerate(sent)
        ]
        return SimpleNamespace(
            exit_code=0,
            stdout=("\n".join(json.dumps(item) for item in responses)).encode(),
        )

    def test_fixed_native_control_reads_plan_after_cleanup_without_a_prompt(self):
        self.agent.container.control.side_effect = self.transport
        snapshot = self.reader.read()
        self.assertEqual(snapshot.submitted_turns, 0)
        self.assertEqual(
            [window.window_minutes for window in snapshot.buckets[0].windows],
            [300, 10080],
        )
        self.agent._check_auth.assert_called_once_with(timeout=15)
        self.agent._prepare_credentials.assert_called_once_with()

    def test_scoped_weekly_windows_are_separate_from_plan_and_billing(self):
        self.payload["rate_limits"].update(
            seven_day_opus={"utilization": 15, "resets_at": None},
            model_scoped=[
                {"display_name": "Fable", "utilization": 8, "resets_at": None}
            ],
            extra_usage={"is_enabled": True, "used_credits": 99},
        )
        snapshot = self.reader.project(self.payload)
        self.assertEqual(
            {bucket.label for bucket in snapshot.buckets}, {"Claude", "Opus", "Fable"}
        )
        self.assertTrue(all(bucket.credits is None for bucket in snapshot.buckets))

    def test_bad_scalars_stay_unknown_and_missing_windows_are_not_invented(self):
        self.payload["rate_limits"] = {
            "five_hour": {"utilization": True, "resets_at": "2030-01-01T12:00:00"}
        }
        window = self.reader.project(self.payload).buckets[0].windows[0]
        self.assertIsNone(window.used_percent)
        self.assertIsNone(window.resets_at)
        self.assertEqual(len(self.reader.project(self.payload).buckets[0].windows), 1)

    def test_unavailable_or_structurally_changed_native_payload_is_refused(self):
        for payload in (
            None,
            {},
            {"rate_limits_available": True, "rate_limits": []},
            {"rate_limits_available": True, "rate_limits": {"five_hour": []}},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.reader.project(payload)

    def test_nonfinite_negative_and_overflowing_percentages_stay_unknown(self):
        for percent in (float("nan"), float("inf"), -1, "12", 10**400):
            with self.subTest(percent=type(percent).__name__):
                self.payload["rate_limits"] = {"five_hour": {"utilization": percent}}
                self.assertIsNone(
                    self.reader.project(self.payload).buckets[0].windows[0].used_percent
                )

    def test_unexpected_model_event_never_becomes_a_successful_quota_read(self):
        self.agent.container.control.return_value = SimpleNamespace(
            exit_code=0, stdout=b'{"type":"assistant","private":"do not expose"}\n'
        )
        with self.assertRaises(RunnerError) as failure:
            self.reader.read()
        self.assertNotIn("private", str(failure.exception))
        self.agent._prepare_credentials.assert_not_called()

    def test_native_cleanup_or_auth_failure_never_publishes_a_snapshot(self):
        self.agent.container.control.side_effect = RunnerError(
            "container_termination_unverified"
        )
        with self.assertRaisesRegex(RunnerError, "container_termination_unverified"):
            self.reader.read()

    def test_scoped_labels_cannot_hide_or_reorder_displayed_text(self):
        for label in ("Fable\x7f", "Fable\u202e", "Fable\u200b"):
            with self.subTest(label=repr(label)):
                self.payload["rate_limits"]["model_scoped"] = [
                    {"display_name": label, "utilization": 1, "resets_at": None}
                ]
                with self.assertRaises(ValueError):
                    self.reader.project(self.payload)
