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
    def test_refusals_without_runs_have_redacted_host_diagnostics(self):
        """Retain status/category/OS family without paths, payloads or tracebacks."""
        runner = Mock(api_token="x" * 32)
        with patch(
            "laomedo.host.runner.http.server.Settings",
            return_value=SimpleNamespace(startup_gate=""),
        ):
            server = RunnerServer(runner, port=0)
        with RunningHTTPServer(server) as running:
            for failure, expected in (
                (RunnerError("future_runner_failure_v2"), "future_runner_failure_v2"),
                (RunnerError("invalid_runner_api_token"), "invalid_runner_api_token"),
                (
                    PermissionError(13, "private credential /private/file"),
                    "runner_unclassified_failure",
                ),
                (
                    ValueError("Bearer private-value https://private.test"),
                    "runner_unclassified_failure",
                ),
                (KeyError("private-key"), "runner_unclassified_failure"),
            ):
                runner.start.side_effect = failure
                request = Request(
                    f"http://127.0.0.1:{running.server_port}/v1/runs",
                    data=b'{"task":"private-task"}',
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer " + "x" * 32,
                    },
                )
                with (
                    self.subTest(failure=type(failure).__name__),
                    self.assertLogs(
                        "laomedo.host.runner.http.handler", level="WARNING"
                    ) as captured,
                ):
                    with self.assertRaises(HTTPError) as response:
                        urlopen(request, timeout=5)
                    with response.exception as error_response:
                        payload = json.load(error_response)
                    diagnostics = payload["runner_diagnostics"]
                text = " ".join(captured.output)
                self.assertIn('"http_status": 400', text)
                self.assertEqual(diagnostics["http_status"], 400)
                self.assertEqual(diagnostics["runner_code"], expected)
                self.assertEqual(diagnostics["stage"], "runner_request")
                self.assertIn(diagnostics["diagnostic_id"], text)
                for private in (
                    "private",
                    "Bearer",
                    "http://",
                    "https://",
                    "Traceback",
                    "x" * 32,
                ):
                    self.assertNotIn(private, text)
                if isinstance(failure, PermissionError):
                    self.assertEqual(diagnostics["failure_kind"], "os_error")
                    self.assertEqual(diagnostics["errno"], 13)

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
                    payload = json.load(response)
                    self.assertIn("runner_diagnostics", payload)
                    self.assertEqual(
                        {
                            key: value
                            for key, value in payload.items()
                            if key != "runner_diagnostics"
                        },
                        {"status": "failed", "error_category": code},
                    )
        self.assertEqual(runner.start.call_count, 2)
