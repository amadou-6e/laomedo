"""No-model Docker proof that only the run capability reaches the agent."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

from laomedo.local_runner import IMAGE, _docker_prefix
from laomedo.github_mediation import MediationStore
from laomedo.mediation_service import MediationHTTPService


@unittest.skipUnless(os.environ.get("LAOMEDO_DOCKER_MEDIATION_TEST") == "1",
                     "requires the pinned local Docker image and Desktop route")
class AgentMediationContainerTests(unittest.TestCase):
    def _call_from_container(self, capability: Path, root: Path, port: int,
                             instance: str):
        workspace, canonical, store = (root / name for name in
                                       ("workspace", "canonical", "store"))
        for path in (workspace, canonical, store):
            path.mkdir(exist_ok=True)
        url = f"http://host.docker.internal:{port}/v1/mediate"
        command = ["docker", *_docker_prefix(
            workspace, canonical, store, capability=capability,
            mediator_url=url, mediator_instance=instance)]
        command = command[:command.index(IMAGE) + 1] + [
            "node", "/run/laomedo/mediate.mjs"]
        self.assertNotIn(capability.read_text(encoding="utf-8").strip(),
                         " ".join(command))
        self.assertIn("--cap-drop", command)
        self.assertIn("no-new-privileges", command)
        return subprocess.run(command, input=json.dumps({
            "repository": "example/disposable", "operation": "actions_read",
            "payload": {}}), text=True, capture_output=True, timeout=30)

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
            result = self._call_from_container(
                capability, Path(directory), server.server_port, "a" * 32)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"ok": True})
        self.assertEqual(seen, [("/v1/mediate", "Bearer synthetic-run-capability",
                                 "a" * 32,
                                 {"repository": "example/disposable",
                                  "operation": "actions_read", "payload": {}})])

    def test_revoked_capability_is_denied_while_second_run_still_works(self):
        if os.name != "nt":
            self.skipTest("host.docker.internal loopback route only checked on Windows")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mediator = MediationStore(root / "mediator.sqlite")
            _, a = mediator.issue(run_id="run-a", invocation_id="invocation-a",
                                  repository="example/disposable", branch="branch-a",
                                  operations={"actions_read"}, ttl_seconds=60)
            _, b = mediator.issue(run_id="run-b", invocation_id="invocation-b",
                                  repository="example/disposable", branch="branch-b",
                                  operations={"actions_read"}, ttl_seconds=60)
            calls = []

            def fake_transport(repository, operation, payload):
                calls.append((repository, operation, payload))
                return {"receipt": len(calls)}

            service = MediationHTTPService(mediator, fake_transport)
            thread = threading.Thread(target=service.serve, daemon=True)
            thread.start()
            self.addCleanup(lambda: (service.close(), thread.join(2)))
            a_file, b_file = root / "a.capability", root / "b.capability"
            a_file.write_text(a + "\n", encoding="utf-8")
            b_file.write_text(b + "\n", encoding="utf-8")
            a_file.chmod(0o600)
            b_file.chmod(0o600)

            first = self._call_from_container(a_file, root, service.port,
                                              service.instance)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(json.loads(first.stdout),
                             {"state": "confirmed", "result": {"receipt": 1}})
            self.assertEqual(mediator.revoke_run("run-a"), 1)
            denied = self._call_from_container(a_file, root, service.port,
                                               service.instance)
            self.assertEqual(denied.returncode, 1, denied.stderr)
            self.assertEqual(json.loads(denied.stdout), {"error": "grant_unavailable"})
            second = self._call_from_container(b_file, root, service.port,
                                               service.instance)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(json.loads(second.stdout),
                             {"state": "confirmed", "result": {"receipt": 2}})
            self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
