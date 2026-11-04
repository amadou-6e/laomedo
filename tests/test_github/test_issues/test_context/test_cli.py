"""Module entrypoint admission and output; internal controls without GitHub."""

import io
import json
import runpy
import sys
import unittest
from unittest.mock import patch

from laomedo.github.issues.errors import IssueContextError


class ContextCliTests(unittest.TestCase):
    """Exercise the real module guard with independently selected reader outcomes."""

    def test_context_cli_main_and_module_guard_still_run_the_reader(self):
        for outcome, status in (
            ({"issue": {"number": 7}}, 0),
            (IssueContextError("issue_unavailable"), 2),
        ):
            output = io.StringIO()
            with (
                patch(
                    "laomedo.github.issues.context_reader.fetch_context",
                    side_effect=outcome if isinstance(outcome, Exception) else None,
                    return_value=outcome,
                ) as reader,
                patch.object(
                    sys, "argv", ["context", "Owner/Repo", "7", "--target-pr", "9"]
                ),
                patch("sys.stdout", output),
                self.assertRaises(SystemExit) as caught,
            ):
                runpy.run_module("laomedo.github.issues.context", run_name="__main__")
            self.assertEqual(caught.exception.code, status)
            reader.assert_called_once_with("Owner/Repo", 7, supplied_target_pr=9)
            self.assertEqual(
                json.loads(output.getvalue()),
                {"error": "issue_unavailable"} if status else outcome,
            )
