"""Private GitHub listeners reject unsafe configuration before binding sockets."""

from http.server import ThreadingHTTPServer
import unittest
from unittest.mock import patch

from laomedo.github.interface.issues.server import IssueServer
from laomedo.github.interface.pull_requests.server import PullRequestServer


class GitHubListenerAdmissionTests(unittest.TestCase):
    def test_token_and_host_admission_precede_socket_creation(self):
        for server, code in (
            (IssueServer, "private_issue_service_required"),
            (PullRequestServer, "private_pr_service_required"),
        ):
            for token in (None, 42, "", "short", "a" * 31):
                with self.subTest(
                    server=server.__name__, token_type=type(token).__name__
                ):
                    with patch.object(ThreadingHTTPServer, "__init__") as bind:
                        with self.assertRaisesRegex(ValueError, "^" + code + "$"):
                            server(object(), token, port=0)
                        bind.assert_not_called()
            for host in ("0.0.0.0", "192.0.2.1", "localhost", "::1"):
                with self.subTest(server=server.__name__, host=host):
                    with patch.object(ThreadingHTTPServer, "__init__") as bind:
                        with self.assertRaisesRegex(ValueError, "^" + code + "$"):
                            server(object(), "a" * 32, port=0, host=host)
                        bind.assert_not_called()
