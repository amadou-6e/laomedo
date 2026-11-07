"""Local socket controls for bridge credentials; not provider acceptance."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from uuid import uuid4

from laomedo.agents.interface.bridge import HttpAgentBridge
from laomedo.integrations.langflow.join.transport import RunnerHTTPTransport
from support.http_server import RunningHTTPServer


class BridgeRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.requests.append((self.command, self.path))
        if self.server.redirect:
            self.send_response(302)
            self.send_header("Location", self.server.redirect)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(self.server.payload).encode())

    do_POST = do_GET

    def log_message(self, *_):
        pass


class BridgeTransportTests(unittest.TestCase):
    def setUp(self):
        private = tempfile.TemporaryDirectory()
        self.addCleanup(private.cleanup)
        self.token = Path(private.name) / "token"
        self.token.write_text("a" * 64, encoding="utf-8")

    def server(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), BridgeRequestHandler)
        server.requests = []
        server.redirect = None
        server.payload = {"run_id": str(uuid4()), "status": "completed"}
        return self.enterContext(RunningHTTPServer(server))

    def bridge(self, server):
        return HttpAgentBridge(
            {"codex": f"http://127.0.0.1:{server.server_port}"},
            {"codex": self.token},
        )

    def test_machine_proxy_configuration_is_not_discovered(self):
        server = self.server()
        # urllib getproxies includes Windows registry settings. Explicit empty
        # ProxyHandler must avoid discovery altogether, not just NO_PROXY.
        with patch(
            "urllib.request.getproxies", side_effect=AssertionError("proxy discovery")
        ):
            bridge = self.bridge(server)
            self.assertEqual(
                bridge.status("codex", server.payload["run_id"])["status"],
                "completed",
            )
            join = RunnerHTTPTransport(bridge.endpoints["codex"], "internal-test-token")
            self.assertEqual(
                join.status(server.payload["run_id"])["status"], "completed"
            )
        self.assertEqual(len(server.requests), 2)

    def test_environment_proxy_receives_no_local_bearer_request(self):
        runner, proxy = self.server(), self.server()
        proxy_url = f"http://127.0.0.1:{proxy.server_port}"
        with patch.dict(
            "os.environ",
            {
                "http_proxy": proxy_url,
                "HTTP_PROXY": proxy_url,
                "no_proxy": "",
                "NO_PROXY": "",
            },
        ):
            bridge = self.bridge(runner)
            result = bridge.status("codex", runner.payload["run_id"])
            join = RunnerHTTPTransport(bridge.endpoints["codex"], "internal-test-token")
            self.assertEqual(
                join.status(runner.payload["run_id"])["status"], "completed"
            )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(runner.requests), 2)
        self.assertEqual(proxy.requests, [])

    def test_redirects_never_contact_destination_for_authenticated_get_or_post(self):
        runner, destination = self.server(), self.server()
        runner.redirect = f"http://127.0.0.1:{destination.server_port}/capture"
        bridge = self.bridge(runner)
        bridge.active["execution"] = (
            bridge.endpoints["codex"],
            runner.payload["run_id"],
        )
        operations = (
            lambda: bridge.status("codex", runner.payload["run_id"]),
            lambda: bridge.lookup_request("codex", str(uuid4())),
            lambda: bridge.cancel("execution"),
            lambda: bridge.select_artifacts(
                {"provider": "codex", "run_id": runner.payload["run_id"]}, ["README.md"]
            ),
        )
        for operation in operations:
            with self.assertRaises(HTTPError) as found:
                operation()
            self.assertEqual(found.exception.code, 302)
            found.exception.close()
        self.assertEqual(len(runner.requests), len(operations))
        self.assertEqual(destination.requests, [])
