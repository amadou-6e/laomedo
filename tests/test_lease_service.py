"""Independent lease service: grant revocation and exact cleanup, no Docker daemon."""

import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib import error, request

from laomedo import lease_service
from laomedo.github_mediation import MediationStore
from laomedo.lease_service import LeaseClient, LeaseService


def _result(directory: Path) -> dict:
    path = directory / "result.json"
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        time.sleep(.01)
    raise AssertionError("lease result not written")


class LeaseServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "service"
        self.cleanups = []

        def cleanup(name, run_id, token):
            self.cleanups.append((name, run_id, token))
            return True, "removed_after_loss"

        self.service = LeaseService(self.state, loss_seconds=.5, cleanup=cleanup)
        self.addCleanup(self.service.server.server_close)

    def register(self, token="token-one"):
        lease_dir = self.state / "leases" / token
        lease_dir.mkdir(parents=True)
        (lease_dir / "heartbeat").write_text(repr(time.time()), encoding="utf-8")
        (lease_dir / "lease.json").write_text(json.dumps(
            {"token": token, "run_id": "run-one", "name": "exact-name"}), encoding="utf-8")
        self.service.tick()
        return lease_dir, (lease_dir / "grant.secret").read_text(encoding="utf-8")

    def test_accepted_lease_gets_an_active_grant(self):
        lease_dir, secret = self.register()
        accepted = json.loads((lease_dir / "accepted.json").read_text(encoding="utf-8"))
        self.assertEqual(accepted["token"], "token-one")
        self.assertEqual(self.service.book.check(secret), (True, accepted["grant_id"]))
        self.assertEqual(self.service.book.check("not-a-grant"), (False, None))

    def test_stale_heartbeat_revokes_grant_before_exact_cleanup(self):
        lease_dir, secret = self.register()
        (lease_dir / "heartbeat").write_text(repr(time.time() - 10), encoding="utf-8")
        self.service.tick()
        result = _result(lease_dir)
        self.assertEqual(result["reason"], "heartbeat_lost")
        self.assertTrue(result["cleanup_verified"])
        self.assertEqual(len(result["revoked_grants"]), 1)
        self.assertLessEqual(result["revoked_at"], result["cleanup_finished_at"])
        self.assertEqual(self.cleanups, [("exact-name", "run-one", "token-one")])
        self.assertEqual(self.service.book.check(secret)[0], False)
        self.service.tick()  # a finished lease is never processed twice
        self.assertEqual(len(self.cleanups), 1)

    def test_fresh_heartbeat_renews_and_unrenewed_grant_expires(self):
        lease_dir, secret = self.register()
        self.service.tick()
        self.assertTrue(self.service.book.check(secret)[0])
        for grant in self.service.book.by_digest.values():
            grant["expires_at"] = time.time() - 1   # simulate a missed renewal window
        self.assertFalse(self.service.book.check(secret)[0])

    def test_done_revokes_grant_and_checks_absence(self):
        lease_dir, secret = self.register()
        (lease_dir / "done").write_text("done", encoding="utf-8")
        with patch("laomedo.lease_service.inspect_exact", return_value=("absent", None)):
            self.service.tick()
            result = _result(lease_dir)
        self.assertEqual((result["reason"], result["cleanup_verified"]), ("done", True))
        self.assertFalse(self.service.book.check(secret)[0])
        self.assertEqual(self.cleanups, [])

    def test_malformed_lease_is_ignored(self):
        lease_dir = self.state / "leases" / "token-two"
        lease_dir.mkdir(parents=True)
        (lease_dir / "lease.json").write_text(json.dumps(
            {"token": "other", "run_id": "run", "name": "n"}), encoding="utf-8")
        self.service.tick()
        self.assertEqual(_result(lease_dir)["reason"], "refused")
        self.assertFalse((lease_dir / "accepted.json").exists())

    def test_http_write_endpoint_accepts_only_active_grant(self):
        lease_dir, secret = self.register()
        thread = threading.Thread(target=self.service.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.service.server.shutdown)
        url = f"http://127.0.0.1:{self.service.port}/write"

        def write(token):
            req = request.Request(url, data=b"{}", method="POST",
                                  headers={"Authorization": "Bearer " + token})
            try:
                with request.urlopen(req, timeout=5) as response:
                    return response.status
            except error.HTTPError as exc:
                return exc.code

        self.assertEqual(write(secret), 200)
        (lease_dir / "heartbeat").write_text(repr(time.time() - 10), encoding="utf-8")
        self.service.tick()
        self.assertEqual(write(secret), 403)
        events = [json.loads(line) for line in
                  (self.state / "grant-events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([event["accepted"] for event in events], [True, False])


class LeaseClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "service"

    def test_client_refuses_missing_or_stale_service(self):
        with self.assertRaisesRegex(RuntimeError, "lease_service_unavailable"):
            LeaseClient(self.state, run_id="r", name="n", token="t",
                        cancelled=threading.Event())
        self.state.mkdir(parents=True)
        (self.state / "service.json").write_text(json.dumps(
            {"pid": -1, "port": 1, "instance": "i"}), encoding="utf-8")
        (self.state / "service.alive").write_text(repr(time.time() - 60), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "lease_service_unavailable"):
            LeaseClient(self.state, run_id="r", name="n", token="t",
                        cancelled=threading.Event())

    def test_client_registers_heartbeats_and_finishes_with_live_service(self):
        service = LeaseService(self.state, loss_seconds=5)
        runner = threading.Thread(target=service.serve, daemon=True)
        runner.start()
        self.addCleanup(service.stopping.set)
        deadline = time.monotonic() + 5
        while not (self.state / "service.alive").exists() and time.monotonic() < deadline:
            time.sleep(.05)
        cancelled = threading.Event()
        # The service runs in-thread here; production refuses a same-process service.
        with patch("laomedo.lease_service.os.getpid", return_value=-2):
            client = LeaseClient(self.state, run_id="run-one", name="exact-name",
                                 token="token-one", cancelled=cancelled)
        self.assertTrue(client.grant_id.startswith("grant-"))
        self.assertTrue(service.book.check(client.grant_secret())[0])
        with patch("laomedo.lease_service.inspect_exact", return_value=("absent", None)):
            result = client.finish()
        self.assertEqual(result["reason"], "done")
        self.assertFalse(service.book.check(client.grant_secret())[0])
        self.assertFalse(cancelled.is_set())

    def test_client_publishes_only_complete_registration(self):
        service = LeaseService(self.state, loss_seconds=5)
        runner = threading.Thread(target=service.serve, daemon=True)
        runner.start()
        def stop_service():
            service.stopping.set()
            runner.join(3)
        self.addCleanup(stop_service)
        deadline = time.monotonic() + 5
        while not (self.state / "service.alive").exists() and time.monotonic() < deadline:
            time.sleep(.05)

        original_write = lease_service._write_json
        saw_staged_registration = []

        def checked_write(path, value):
            if path.name == "lease.json":
                self.assertEqual(path.parent.parent, self.state / "pending-leases")
                self.assertFalse((self.state / "leases" / "token-race").exists())
                # Reproduce the scan that previously refused a directory
                # created before its lease.json had been written.
                service.tick()
                saw_staged_registration.append(True)
            original_write(path, value)

        with patch("laomedo.lease_service._write_json", side_effect=checked_write), \
                patch("laomedo.lease_service.os.getpid", return_value=-2):
            client = LeaseClient(self.state, run_id="run-race", name="exact-name",
                                 token="token-race", cancelled=threading.Event())
        self.assertEqual(saw_staged_registration, [True])
        self.assertFalse((client.dir / "result.json").exists())
        self.assertTrue((client.dir / "accepted.json").exists())
        with patch("laomedo.lease_service.inspect_exact", return_value=("absent", None)):
            client.finish()

    def test_client_reports_service_refusal_without_waiting_for_timeout(self):
        store = MediationStore(Path(self.temp.name) / "mediator.sqlite")
        cleanup_started = threading.Event()
        release_cleanup = threading.Event()
        def slow_cleanup(*_):
            cleanup_started.set()
            release_cleanup.wait(10)
            return True, "synthetic_cleanup"
        service = LeaseService(self.state, mediator=store, cleanup=slow_cleanup)
        runner = threading.Thread(target=service.serve, daemon=True)
        runner.start()
        def stop_service():
            service.stopping.set()
            runner.join(3)
        self.addCleanup(stop_service)
        deadline = time.monotonic() + 5
        while not (self.state / "service.alive").exists() and time.monotonic() < deadline:
            time.sleep(.05)
        try:
            with patch("laomedo.lease_service.os.getpid", return_value=-2):
                with self.assertRaisesRegex(
                        RuntimeError, "lease_service_refused:mediated_lease_not_authorized"):
                    LeaseClient(self.state, run_id="r", name="n", token="t",
                                cancelled=threading.Event(),
                                mediation_request={"invocation_id": "i",
                                                   "repository": "example/disposable",
                                                   "branch": "probe-r"})
            self.assertTrue(cleanup_started.wait(2))
            self.assertFalse((self.state / "leases" / "t" / "result.json").exists())
        finally:
            release_cleanup.set()


if __name__ == "__main__":
    unittest.main()
