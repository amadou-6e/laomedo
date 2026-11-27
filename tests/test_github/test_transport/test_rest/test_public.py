"""Public issue reads never use credentials or admit GitHub writes."""

import io
import unittest
from unittest.mock import MagicMock, Mock

from laomedo.github.transport.rest.public import PublicGitHubIssueTransport
from laomedo.host.mediation.errors import KnownRejected


class PublicGitHubIssueTransportTests(unittest.TestCase):
    def test_reads_are_anonymous_and_repo_scoped(self):
        response = io.BytesIO(b'[{"name":"bug"}]')
        opener = Mock()
        opener.open.return_value = MagicMock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        transport = PublicGitHubIssueTransport("owner/repo", opener=opener)
        self.assertEqual(
            transport("owner/repo", "label_list", {}), {"items": [{"name": "bug"}]}
        )
        call = opener.open.call_args.args[0]
        self.assertEqual(
            call.full_url,
            "https://api.github.com/repos/owner/repo/labels?per_page=100&page=1",
        )
        self.assertIsNone(call.get_header("Authorization"))
        with self.assertRaises(KnownRejected):
            transport("other/repo", "label_list", {})

    def test_every_write_operation_is_refused_without_network(self):
        opener = Mock()
        transport = PublicGitHubIssueTransport("owner/repo", opener=opener)
        with self.assertRaises(KnownRejected):
            transport("owner/repo", "issue_patch", {})
        with self.assertRaises(KnownRejected):
            transport._call("PATCH", "/repos/owner/repo/issues/1", {})
        opener.open.assert_not_called()
        with self.assertRaises(ValueError):
            PublicGitHubIssueTransport("owner/..", opener=opener)
