"""Internal byte compatibility and redaction controls, not login acceptance."""

import base64
import json
from pathlib import Path
import unittest

from laomedo.agents.agents.claude.auth.errors import LocalClaudeLoginError
from laomedo.agents.agents.claude.auth.models import ClaudeAccessLoginRecord


class ClaudeAccessLoginRecordTests(unittest.TestCase):
    def test_exact_pinned_old_writer_bytes(self):
        oracle = json.loads(
            Path(__file__)
            .with_name("contracts")
            .joinpath("claude-access-login-3299f8d.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(oracle["revision"], "3299f8df976965b707e7c91d3309ea2e8e0aaadf")
        self.assertEqual(len(oracle["cases"]), 96)
        for case in oracle["cases"]:
            with self.subTest(
                expiry_type=case["expiry_type"],
                variant=case["optional_variant"],
                mask=case["optional_mask"],
            ):
                value = json.loads(case["input_json"])
                record = ClaudeAccessLoginRecord.from_host_record(value)
                self.assertEqual(
                    record.to_private_bytes(), base64.b64decode(case["bytes_base64"])
                )
                self.assertIs(type(record.expires_at), type(value["expiresAt"]))
                self.assertEqual(record.model_dump(), {})
                self.assertEqual(record.model_dump_json(), "{}")

    def test_refresh_and_unrelated_host_values_never_enter_the_record(self):
        value = {
            "accessToken": "synthetic-access",
            "expiresAt": 1234567890123,
            "refreshToken": "synthetic-refresh-must-not-copy",
            "unrelated": "synthetic-private-state",
        }
        record = ClaudeAccessLoginRecord.from_host_record(value)
        self.assertNotIn("synthetic", repr(record))
        self.assertNotIn("refresh", record.model_fields_set)
        self.assertNotIn("synthetic-refresh", record.to_private_bytes().decode())
        self.assertNotIn("unrelated", record.to_private_bytes().decode())
        self.assertEqual(
            json.loads(record.to_private_bytes())["claudeAiOauth"]["refreshToken"], ""
        )

    def test_original_manual_admission_and_fixed_expiry_threshold(self):
        for value in (
            None,
            [],
            "text",
            {},
            {"accessToken": "x", "expiresAt": True},
            {"accessToken": "", "expiresAt": 1},
            {"accessToken": "x", "expiresAt": float("inf")},
            {"accessToken": "x", "expiresAt": float("nan")},
        ):
            with self.subTest(kind=type(value).__name__):
                with self.assertRaisesRegex(
                    LocalClaudeLoginError, "claude_host_login_unavailable"
                ):
                    ClaudeAccessLoginRecord.from_host_record(value)
        record = ClaudeAccessLoginRecord.from_host_record(
            {"accessToken": "x", "expiresAt": 1000}
        )
        record.require_expiry_after(999)
        with self.assertRaisesRegex(LocalClaudeLoginError, "claude_host_login_expired"):
            record.require_expiry_after(1000)

    def test_deep_native_json_has_no_new_model_recursion_limit(self):
        nested = None
        for _ in range(300):
            nested = [nested]
        value = {"accessToken": "synthetic-access", "expiresAt": 1000, "scopes": nested}
        record = ClaudeAccessLoginRecord.from_host_record(value)
        self.assertEqual(
            record.to_private_bytes(),
            json.dumps({"claudeAiOauth": {**value, "refreshToken": ""}}).encode(),
        )


if __name__ == "__main__":
    unittest.main()
