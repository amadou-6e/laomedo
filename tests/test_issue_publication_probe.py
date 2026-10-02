"""EXP-14: a lost GitHub acknowledgement is unknown, never a blind retry."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Thread
import unittest


PROBE_PATH = Path(__file__).parents[1] / "experiments/issue-integration/44/probe.py"
SPEC = importlib.util.spec_from_file_location("publication_probe_44", PROBE_PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class FakeGitHub(BaseHTTPRequestHandler):
    ledger: Path

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        entry = {
            "proposal_id": self.headers["X-Proposal-Id"],
            "attempt_id": self.headers["X-Attempt-Id"],
            "payload": json.loads(body),
        }
        with self.ledger.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        response = json.dumps({"number": 123, "html_url": "http://fake/issues/123"}).encode()
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *_):
        pass


class PublicationFaultTests(unittest.TestCase):
    def setUp(self):
        self.private = tempfile.TemporaryDirectory()
        self.addCleanup(self.private.cleanup)
        root = Path(self.private.name)
        self.intent = root / "intent.json"
        self.ledger = root / "fake-server-ledger.jsonl"
        handler = type("FixtureGitHub", (FakeGitHub,), {"ledger": self.ledger})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}/issues"

    def prepare(self):
        probe.prepare(self.intent, proposal_id="proposal-1", title="Fixture failure",
                      body="Synthetic report", reviewed_by="fixture-user",
                      decision="publish")

    def worker(self, phase):
        return subprocess.run(
            [sys.executable, str(PROBE_PATH), str(self.intent), self.url,
             "--crash-at", phase], capture_output=True, text=True, timeout=15,
        )

    def entries(self):
        if not self.ledger.exists():
            return []
        return [json.loads(line) for line in self.ledger.read_text(encoding="utf-8").splitlines()]

    def test_before_send_is_conservatively_unknown_and_not_retried(self):
        self.prepare()
        self.assertEqual(self.worker("before_send").returncode, 17)
        self.assertEqual(self.entries(), [])
        self.assertEqual(probe.inspect(self.intent)["status"], "unknown")
        with self.assertRaisesRegex(probe.ProbeError, "requires_reconciliation"):
            probe.send_once(self.intent, self.url)
        self.assertEqual(self.entries(), [])

    def test_after_remote_acceptance_is_unknown_not_failed_or_published(self):
        self.prepare()
        self.assertEqual(self.worker("after_accept").returncode, 17)
        self.assertEqual(len(self.entries()), 1)
        self.assertEqual(self.entries()[0]["payload"]["title"], "Fixture failure")
        result = probe.inspect(self.intent)
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["issue_number"])
        with self.assertRaisesRegex(probe.ProbeError, "requires_reconciliation"):
            probe.send_once(self.intent, self.url)
        self.assertEqual(len(self.entries()), 1)

    def test_after_response_persistence_is_confirmed_even_if_process_dies(self):
        self.prepare()
        self.assertEqual(self.worker("after_response_recorded").returncode, 17)
        self.assertEqual(len(self.entries()), 1)
        result = probe.inspect(self.intent)
        self.assertEqual(result["status"], "published")
        self.assertEqual(result["issue_number"], 123)

    def test_review_gate_tamper_and_nonlocal_endpoint(self):
        with self.assertRaisesRegex(probe.ProbeError, "not_reviewed"):
            probe.prepare(self.intent, proposal_id="proposal-1", title="Fixture",
                          body="Synthetic", reviewed_by="", decision="publish")
        self.prepare()
        record = json.loads(self.intent.read_text(encoding="utf-8"))
        record["reviewed_body"] = "changed after review"
        self.intent.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaisesRegex(probe.ProbeError, "reviewed_bytes_changed"):
            probe.send_once(self.intent, self.url)
        self.assertEqual(self.entries(), [])
        with self.assertRaisesRegex(probe.ProbeError, "fake_local_endpoint_required"):
            probe.send_once(self.intent, "https://api.github.com/repos/x/y/issues")
        with self.assertRaisesRegex(probe.ProbeError, "fake_local_endpoint_required"):
            probe.send_once(self.intent, "http://127.0.0.1:80@github.com/issues")


if __name__ == "__main__":
    unittest.main()
