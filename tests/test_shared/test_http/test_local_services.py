"""Local socket credential boundaries; synthetic responses are internal only."""

from http.server import ThreadingHTTPServer
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from laomedo.agents.agents.claude.http.commands import ClaudeCommandTransport
from laomedo.agents.agents.codex.agent import CodexAgent
from laomedo.agents.errors import RunnerError
from laomedo.work_graph.client import LangflowLocalClient
from laomedo.work_graph.runs.errors import LaunchError
from support.http_server import RecordingJSONHandler, RunningHTTPServer


class LocalServiceTransportTests(unittest.TestCase):
    def setUp(self):
        private = tempfile.TemporaryDirectory()
        self.addCleanup(private.cleanup)
        self.servers = ExitStack()
        self.addCleanup(self.servers.close)
        self.root = Path(private.name)
        self.secret = self.root / "secret"
        self.secret.write_text("a" * 64)

    def server(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingJSONHandler)
        server.requests = []
        server.redirect = None
        server.payload = {"access_token": "internal-test-token", "accepted": True}
        return self.servers.enter_context(RunningHTTPServer(server))

    def service(self, server):
        executor = SimpleNamespace()
        service = object.__new__(ClaudeCommandTransport)
        service.executor = executor
        service.executor.closed = False
        service.executor.cancelled = Event()
        service.executor.mediation = (
            f"http://127.0.0.1:{server.server_port}/mediate",
            "a" * 32,
            self.secret,
        )
        service.executor.record = {"github_scope": {"repository": "owner/repository"}}
        return service

    def test_mediation_and_local_app_login_ignore_machine_proxies(self):
        server, proxy = self.server(), self.server()
        proxy_url = f"http://127.0.0.1:{proxy.server_port}"
        with (
            patch.dict(
                "os.environ",
                {
                    "http_proxy": proxy_url,
                    "HTTP_PROXY": proxy_url,
                    "NO_PROXY": "",
                    "no_proxy": "",
                },
            ),
            patch(
                "urllib.request.getproxies",
                side_effect=AssertionError("machine proxy discovery"),
            ),
        ):
            service = self.service(server)
            self.assertTrue(
                service.mediate({"operation": "read", "payload": {}})["accepted"]
            )
            client = LangflowLocalClient(f"http://127.0.0.1:{server.server_port}")
            self.assertTrue(client.fetch("flow")["accepted"])
        self.assertEqual(len(server.requests), 3)
        self.assertEqual(proxy.requests, [])

    def test_redirects_do_not_forward_mediation_or_local_app_credentials(self):
        server, destination = self.server(), self.server()
        client = LangflowLocalClient(f"http://127.0.0.1:{server.server_port}")
        server.redirect = f"http://127.0.0.1:{destination.server_port}/capture"
        service = self.service(server)
        with self.assertRaisesRegex(RunnerError, "claude_mediation_outcome_unknown"):
            service.mediate({"operation": "read", "payload": {}})
        self.assertTrue(service.executor.cancelled.is_set())
        self.assertEqual(service.executor.record["mediation_outcome"], "unknown")
        with self.assertRaisesRegex(LaunchError, "saved_flow_fetch_failed"):
            client.fetch("flow")
        with self.assertRaisesRegex(LaunchError, "langflow_local_login_unavailable"):
            LangflowLocalClient(f"http://127.0.0.1:{server.server_port}")
        self.assertEqual(destination.requests, [])

    def test_mediation_keeps_known_refusal_separate_from_uncertain_server_failure(self):
        server = self.server()
        server.response_status = 403
        service = self.service(server)
        self.assertEqual(
            service.mediate({"operation": "read", "payload": {}}),
            {"error": "mediation_request_refused"},
        )
        self.assertFalse(service.executor.cancelled.is_set())
        server.response_status = 503
        with self.assertRaisesRegex(RunnerError, "claude_mediation_outcome_unknown"):
            service.mediate({"operation": "read", "payload": {}})
        self.assertTrue(service.executor.cancelled.is_set())

    def test_mediator_health_ignores_proxies_and_refuses_redirects(self):
        server, destination = self.server(), self.server()
        server.payload = {"status": "ready", "instance": "a" * 32}
        (self.root / "mediator.json").write_text(
            json.dumps({"port": server.server_port, "instance": "a" * 32})
        )
        runner = object.__new__(CodexAgent)
        runner.mediator_state = self.root
        with (
            patch("laomedo.agents.agents.base.agent.os", SimpleNamespace(name="nt")),
            patch(
                "urllib.request.getproxies",
                side_effect=AssertionError("machine proxy discovery"),
            ),
        ):
            self.assertEqual(runner._mediator_route()[1], "a" * 32)
            server.redirect = f"http://127.0.0.1:{destination.server_port}/health"
            with self.assertRaisesRegex(RunnerError, "mediator_unavailable"):
                runner._mediator_route()
        self.assertEqual(destination.requests, [])
