"""Registry failures keep their public machine category across the HTTP boundary."""

import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from laomedo.host.runner.http.server import RunnerServer
from laomedo.agents.errors import RunnerError
from laomedo.skills.registry.errors import SkillStoreError
from support.http_server import RunningHTTPServer


class RunnerHTTPErrorTests(unittest.TestCase):
    def test_refused_resume_does_not_release_another_attempts_mcp_grant(self):
        """A failed binding owns no capability and must not revoke an active run."""
        runner = Mock(api_token="x" * 32)
        runner.bind_mcp_resume.side_effect = RunnerError("mcp_run_already_bound")
        with patch(
            "laomedo.host.runner.http.server.Settings",
            return_value=SimpleNamespace(startup_gate=""),
        ):
            server = RunnerServer(runner, port=0)
        with RunningHTTPServer(server) as running:
            request = Request(
                f"http://127.0.0.1:{running.server_port}/v1/runs/existing/resume",
                data=b"{}",
                headers={
                    "Authorization": "Bearer " + "x" * 32,
                    "Content-Type": "application/json",
                },
            )
            with self.assertRaises(HTTPError) as failure:
                urlopen(request, timeout=5)
            with failure.exception as response:
                self.assertEqual(
                    json.load(response)["error_category"], "mcp_run_already_bound"
                )
        runner.release_mcp.assert_not_called()
        runner.prepare_resume.assert_not_called()

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
