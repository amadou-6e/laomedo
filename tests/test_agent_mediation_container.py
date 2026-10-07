"""No-model Docker proof that only the run capability reaches the agent."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

from laomedo.local_runner import IMAGE, MEDIATION_CLIENT


@unittest.skipUnless(os.environ.get("LAOMEDO_DOCKER_MEDIATION_TEST") == "1",
                     "requires the pinned local Docker image and Desktop route")
class AgentMediationContainerTests(unittest.TestCase):
    def test_readonly_capability_calls_host_without_provider_credential(self):
        if os.name != "nt":
            self.skipTest("host.docker.internal loopback route only checked on Windows")
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                seen.append((self.path, self.headers.get("Authorization"), json.loads(body)))
                data = b'{"ok":true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as directory:
            capability = Path(directory) / "capability"
            capability.write_text("synthetic-run-capability\n", encoding="utf-8")
            url = f"http://host.docker.internal:{server.server_port}/v1/mediate"
            command = ["docker", "run", "--rm", "-i", "--pull=never",
                       "--network", "bridge", "--user", "10001:10001",
                       "--mount", f"type=bind,source={capability},target=/run/laomedo/capability,readonly",
                       "--mount", f"type=bind,source={MEDIATION_CLIENT},target=/run/laomedo/mediate.mjs,readonly",
                       "--env", "LAOMEDO_MEDIATOR_URL=" + url,
                       "--env", "LAOMEDO_CAPABILITY_FILE=/run/laomedo/capability",
                       IMAGE, "node", "/run/laomedo/mediate.mjs"]
            self.assertNotIn("synthetic-run-capability", " ".join(command))
            result = subprocess.run(command, input=json.dumps({
                "repository": "example/disposable", "operation": "actions_read",
                "payload": {}}), text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"ok": True})
        self.assertEqual(seen, [("/v1/mediate", "Bearer synthetic-run-capability",
                                 {"repository": "example/disposable",
                                  "operation": "actions_read", "payload": {}})])


if __name__ == "__main__":
    unittest.main()
