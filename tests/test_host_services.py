"""Synthetic host-service composition; no GitHub or model call."""

import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.request import urlopen

from laomedo.host_services import build_services, serve_services
from laomedo.local_runner import LocalRunner, RunnerError


class HostServicesTests(unittest.TestCase):
    def test_both_services_start_outside_agent_mount_with_no_token_in_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token_file = root / "private.env"
            token_file.write_text("GH=synthetic-provider-secret\n", encoding="utf-8")
            checkout = root / "checkout"
            checkout.mkdir()
            agent_mount = root / "agent"
            agent_mount.mkdir()
            state = root / "host-state"
            lease, mediator = build_services(
                state=state, repository="example/disposable", checkout=checkout,
                baseline="a" * 40, agent_mount=agent_mount,
                connection_id="synthetic", connection_generation=1,
                token_file=token_file)
            thread = threading.Thread(target=serve_services, args=(lease, mediator, state),
                                      kwargs={"repository": "example/disposable",
                                              "connection_id": "synthetic",
                                              "connection_generation": 1}, daemon=True)
            thread.start()
            try:
                deadline = time.monotonic() + 5
                while not (state / "lease" / "service.alive").exists():
                    if time.monotonic() > deadline:
                        self.fail("lease service did not start")
                    time.sleep(.01)
                status = json.loads((state / "mediator" / "mediator.json").read_text(
                    encoding="utf-8"))
                with urlopen(f"http://127.0.0.1:{status['port']}/v1/health",
                             timeout=2) as response:
                    self.assertEqual(json.load(response),
                                     {"status": "ready", "instance": status["instance"]})
                self.assertEqual(lease.server.server_address[0], "127.0.0.1")
                self.assertNotIn("synthetic-provider-secret", json.dumps(status))
                self.assertFalse((agent_mount / "private.env").exists())
                if os.name == "nt":
                    runner = LocalRunner.__new__(LocalRunner)
                    runner.mediator_state = state / "mediator"
                    self.assertEqual(runner._mediator_url(),
                                     f"http://host.docker.internal:{status['port']}/v1/mediate")
                    path = state / "mediator" / "mediator.json"
                    path.write_text(json.dumps({**status, "instance": "0" * 32}),
                                    encoding="utf-8")
                    with self.assertRaisesRegex(RunnerError, "mediator_unavailable"):
                        runner._mediator_url()
            finally:
                lease.stopping.set()
                thread.join(timeout=5)
            self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
