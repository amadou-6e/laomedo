"""Secret masking controls, including a bounded worker for pathological input."""

import subprocess
import sys
import unittest

from session_retro.redaction import Redactor


class RedactionTests(unittest.TestCase):
    """Check supported masking and guard against a single-record regex hang."""

    def test_long_keyword_free_identifiers_finish_in_a_bounded_worker(self):
        """A 1MiB identifier must not trigger suffix-by-suffix keyword scanning."""
        subprocess.run(
            [
                sys.executable,
                "-c",
                "from session_retro.redaction import Redactor; value='A'*(1024*1024); assert Redactor().text(value)==value",
            ],
            check=True,
            timeout=15,
            capture_output=True,
        )

    def test_sensitive_keys_and_ordinary_values_remain_distinct(self):
        """Preserve ordinary assignments and redact supported key spellings."""
        redactor = Redactor()
        for key in ("accessToken", "api-key", "password", "client_secret"):
            self.assertNotIn(
                "private-value", redactor.text(f'"{key}": "private-value"')
            )
        self.assertEqual(
            redactor.text('"description": "keep this"'), '"description": "keep this"'
        )
        self.assertEqual(
            redactor.text("MY_API_KEY=private-value"), "MY_API_KEY=[REDACTED]"
        )
        self.assertEqual(redactor.text("password=private-value"), "password=[REDACTED]")
