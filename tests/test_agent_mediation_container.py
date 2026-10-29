"""No-model Docker proof that only the run capability reaches the agent."""

from http.server import BaseHTTPRequestHandler; from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

from laomedo.agents.agents.codex.settings import IMAGE; from laomedo.agents.agents.codex.controller.models import CodexLaunch


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
                seen.append((self.path, self.headers.get("Authorization"),
                             self.headers.get("X-Laomedo-Mediator-Instance"),
                             json.loads(body)))
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
            capability.chmod(0o600)
            workspace, canonical, store = (Path(directory) / name for name in
                                           ("workspace", "canonical", "store"))
            for path in (workspace, canonical, store):
                path.mkdir()
            url = f"http://host.docker.internal:{server.server_port}/v1/mediate"
            from py_docker import Client
            from py_docker.jobs.models import ContainerJob
            from py_docker.streams.models import StreamLimits
            from uuid import uuid4
            with Client() as client:
                spec=CodexLaunch(workspace=workspace,canonical=canonical,store_mount=store,
                    image=client.images.resolve(IMAGE),name="laomedo-mediate-"+uuid4().hex,
                    capability=capability,mediator_url=url,mediator_instance="a"*32).to_container_spec()
                payload=json.dumps({"repository":"example/disposable","operation":"actions_read","payload":{}})
                spec=spec.model_copy(update={"stdin_open":False,"command":["sh","-c",'printf \'%s\' "$1" | node /run/laomedo/mediate.mjs',"request",payload]})
                self.assertNotIn("synthetic-run-capability",spec.model_dump_json())
                self.assertEqual(spec.cap_drop,["ALL"])
                self.assertIn("no-new-privileges",spec.security_opt)
                result=client.jobs.run(ContainerJob(spec=spec,limits=StreamLimits(seconds=30,max_bytes=65536),
                    wait_timeout_seconds=30,receipt_path=Path(directory).joinpath("receipt.json")))
        self.assertEqual(result.exit_code, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"ok": True})
        self.assertEqual(seen, [("/v1/mediate", "Bearer synthetic-run-capability",
                                 "a" * 32,
                                 {"repository": "example/disposable",
                                  "operation": "actions_read", "payload": {}})])


if __name__ == "__main__":
    unittest.main()
