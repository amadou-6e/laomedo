"""Paired private listeners with internal gateways; not GitHub acceptance."""

import json
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import Request, build_opener

from laomedo.github.interface.issues.server import IssueServer
from laomedo.github.interface.pull_requests.server import PullRequestServer
from laomedo.host.http import NoRedirect
from support.http_server import RunningHTTPServer


class GitHubHTTPBindingsTests(unittest.TestCase):
    """Keep request credentials and gateway state bound to each actual server."""

    def _post(self, base, route, token, body):
        call = Request(
            base + route,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            },
        )
        try:
            response = build_opener(NoRedirect()).open(call, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.code, json.loads(response.read()), response.headers

    def test_tokens_and_service_bindings_are_instance_local(self):
        for server_type, route in (
            (IssueServer, "/v1/github-issues/discover"),
            (PullRequestServer, "/v1/github-prs/discover"),
        ):
            with self.subTest(route=route):
                body = {
                    "repository_url": "https://github.com/owner/repo",
                    "labels": [],
                    "state": "open",
                }
                services = [Mock(), Mock()]
                tokens = ["internal-one-" + "a" * 32, "internal-two-" + "b" * 32]
                bases = []
                for index, (service, token) in enumerate(zip(services, tokens)):
                    service.discover.return_value = {"instance": index}
                    server = server_type(service, token, port=0)
                    lifetime = RunningHTTPServer(server)
                    self.addCleanup(lifetime.__exit__, None, None, None)
                    lifetime.__enter__()
                    bases.append(f"http://127.0.0.1:{server.server_port}")
                for index, base in enumerate(bases):
                    refused = self._post(base, route, tokens[1 - index], body)
                    self.assertEqual(
                        refused[:2], (401, {"error_category": "unauthorized"})
                    )
                    services[index].discover.assert_not_called()
                    accepted = self._post(base, route, tokens[index], body)
                    self.assertEqual(accepted[:2], (200, {"instance": index}))
                    self.assertEqual(accepted[2]["Cache-Control"], "no-store")
                    self.assertNotIn(tokens[index], json.dumps(accepted[1]))
