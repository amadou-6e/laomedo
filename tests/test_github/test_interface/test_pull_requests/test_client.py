"""The PR HTTP client preserves only its own admitted public failure codes."""

import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from laomedo.github.interface.pull_requests.client import pr_request
from laomedo.github.issues.contract import ERROR_CODES as ISSUE_CODES
from laomedo.github.pull_requests.contract import ERROR_CODES as PR_CODES


class PRClientErrorContractTests(unittest.TestCase):
    def test_foreign_issue_transport_codes_cannot_be_projected_as_pr_codes(self):
        self.assertIn("github_http_403", ISSUE_CODES)
        self.assertNotIn("github_http_403", PR_CODES)
        for remote, expected in (
            ("github_http_403", "github_pr_unavailable"),
            ("selected_pr_required", "selected_pr_required"),
        ):
            with (
                self.subTest(code=remote),
                io.BytesIO(json.dumps({"error_category": remote}).encode()) as body,
            ):
                opener = Mock()
                opener.open.side_effect = HTTPError(
                    "http://127.0.0.1/", 400, "refused", {}, body
                )
                with (
                    patch(
                        "laomedo.github.interface.pull_requests.client.Settings",
                        return_value=SimpleNamespace(
                            url="http://127.0.0.1:8784",
                            token_file="unused-control-path",
                        ),
                    ),
                    patch(
                        "laomedo.github.interface.pull_requests.client.Path.read_text",
                        return_value="a" * 32,
                    ),
                    patch(
                        "laomedo.github.interface.pull_requests.client.request.build_opener",
                        return_value=opener,
                    ),
                    self.assertRaisesRegex(ValueError, "^" + expected + "$"),
                ):
                    pr_request("discover")
