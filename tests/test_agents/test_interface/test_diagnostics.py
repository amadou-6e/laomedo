"""Future machine codes remain diagnosable without publishing exception payloads."""

import unittest

from laomedo.agents.interface.utils import safe_error_code


class DiagnosticCodeTests(unittest.TestCase):
    """Exercise the same bounded machine-code policy used by graph presentation."""

    def test_known_and_future_codes_survive(self):
        """Explicit known codes and neutral future categories retain their value."""
        for code in ("future_failure_v2", "missing_workspace", "step_42_refused"):
            with self.subTest(code=code):
                self.assertEqual(safe_error_code(code), code)
        self.assertEqual(
            safe_error_code("unauthorized", {"unauthorized"}), "unauthorized"
        )
        self.assertEqual(
            safe_error_code("invalid_runner_api_token", {"invalid_runner_api_token"}),
            "invalid_runner_api_token",
        )

    def test_arbitrary_and_credential_shaped_values_are_redacted(self):
        """Reject free-form errors, token prefixes and sensitive unknown codes."""
        for value in (
            None,
            401,
            {},
            "unauthorized",
            "Bearer private",
            "https://private.test",
            "C:/private/file",
            "ghp_private_value",
            "github_pat_private",
            "sk_private",
            "my_secret_password",
            "custom_bearer_value",
            "unknown_token_failure",
            "my_credential_value",
            "failure_" + "a" * 80,
        ):
            with self.subTest(value=value):
                self.assertIsNone(safe_error_code(value))
