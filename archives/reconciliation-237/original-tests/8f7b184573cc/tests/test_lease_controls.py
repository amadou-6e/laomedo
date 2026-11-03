"""Preserve independent result validation while retrying transient file races."""

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from lease_controls import result


class LeaseResultReaderTests(unittest.TestCase):
    def test_result_disappearing_before_open_is_retried(self):
        with patch.object(
            Path, "read_text", side_effect=[FileNotFoundError(), '{"reason":"done"}']
        ) as read:
            self.assertEqual(result(Path("unused")), {"reason": "done"})
        self.assertEqual(read.call_count, 2)

    def test_transient_windows_read_lock_is_retried(self):
        with patch.object(
            Path, "read_text", side_effect=[PermissionError(), '{"reason":"done"}']
        ):
            self.assertEqual(result(Path("unused")), {"reason": "done"})

    def test_malformed_result_is_still_a_failure(self):
        with patch.object(Path, "read_text", return_value="not JSON"):
            with self.assertRaises(json.JSONDecodeError):
                result(Path("unused"))
