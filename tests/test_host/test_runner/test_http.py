"""Registry failures keep their public machine category across the HTTP boundary."""

import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from laomedo.host.runner.http.server import RunnerServer
from laomedo.skills.registry.errors import SkillStoreError
from support.http_server import RunningHTTPServer


class RunnerHTTPErrorTests(unittest.TestCase):
    def test_registry_error_categories_are_preserved_over_http(self):
        runner = Mock(api_token="x" * 32)
        with patch(
            "laomedo.host.runner.http.server.Settings",
            return_value=SimpleNamespace(startup_gate=""),
        ):
            server = RunnerServer(runner, port=0)
        with RunningHTTPServer(server) as running:
            for code in ("invalid_revision_id", "linked_path"):
                runner.start.side_effect = SkillStoreError(code)
                request = Request(
                    f"http://127.0.0.1:{running.server_port}/v1/runs",
                    data=b"{}",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer " + "x" * 32,
                    },
                )
                with self.subTest(code=code), self.assertRaises(HTTPError) as failure:
                    urlopen(request, timeout=5)
                with failure.exception as response:
                    self.assertEqual(response.code, 400)
                    self.assertEqual(
                        json.load(response),
                        {"status": "failed", "error_category": code},
                    )
        self.assertEqual(runner.start.call_count, 2)
