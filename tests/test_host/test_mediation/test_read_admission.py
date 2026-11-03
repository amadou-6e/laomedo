"""Read admission reaches the current label validator without remote effects."""

import unittest
from laomedo.host.mediation.errors import MediationError
from laomedo.host.mediation.utils import _validate_read


class ReadAdmissionTests(unittest.TestCase):
    def test_current_issue_read_paths_resolve_their_validator(self):
        for operation, payload in (
            ("label_list", {}),
            ("issue_read", {"number": 1}),
            ("issue_query", {"labels": ["bug"], "state": "open"}),
        ):
            with self.subTest(operation=operation):
                self.assertIsNone(
                    _validate_read(operation, payload, "owner/repo", None, None)
                )
        with self.assertRaisesRegex(MediationError, "^issue_read_request_invalid$"):
            _validate_read(
                "issue_query",
                {"labels": "bug", "state": "open"},
                "owner/repo",
                None,
                None,
            )
