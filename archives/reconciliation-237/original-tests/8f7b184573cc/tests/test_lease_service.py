"""Independent lease service: grant revocation and exact cleanup, no Docker daemon."""

from laomedo.host.leases.utils import _read_float as _owned_lease_service__read_float
from laomedo.host.leases.utils import _read_json as _owned_lease_service__read_json
from laomedo.host.leases.utils import _write_float as _owned_lease_service__write_float
from laomedo.host.leases.utils import _write_json as _owned_lease_service__write_json

import json
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib import error
from urllib import request

import laomedo.host.leases.service as lease_service
from laomedo.host.mediation.store import MediationStore
from laomedo.host.leases.client import LeaseClient
from laomedo.host.leases.service import LeaseService
from laomedo.host.leases.settings import LOSS_SECONDS
from lease_controls import result as _result
from lease_controls import wait_for_cleanup


class LeaseServiceTests(unittest.TestCase):
    def test_loss_cleanup_always_publishes_safe_final_callback_observation(self):
        self.service.loss_seconds = 60
        cases = (
            ("nonbool", (1, "private-cleanup-secret"), False, "cleanup_error"),
            (
                "object",
                (True, SimpleNamespace(secret="private-cleanup-secret")),
                False,
                "cleanup_error",
            ),
            (
                "exception-value",
                (True, RuntimeError("private-cleanup-secret")),
                False,
                "cleanup_error",
            ),
            ("raises", RuntimeError("private-cleanup-secret"), False, "cleanup_error"),
            (
                "json",
                (True, {"removed": ["owned"], "unknown": None}),
                True,
                {"removed": ["owned"], "unknown": None},
            ),
            (
                "json-failed",
                (False, {"removed": [], "observed": "running"}),
                False,
                {"removed": [], "observed": "running"},
            ),
        )
        for name, callback_result, verified, detail in cases:
            with self.subTest(case=name):
                lease_dir, secret = self.register("cleanup-" + name)
                (lease_dir / "heartbeat").write_text(
                    repr(time.time() - 120), encoding="utf-8"
                )
                errors = []
                options = (
                    {"side_effect": callback_result}
                    if isinstance(callback_result, Exception)
                    else {"return_value": callback_result}
                )
                with (
                    patch.object(self.service, "cleanup", **options),
                    patch("threading.excepthook", side_effect=errors.append),
                ):
                    self.service.tick()
                    result = _result(lease_dir)
                self.assertEqual(errors, [])
                self.assertEqual(result["reason"], "heartbeat_lost")
                self.assertIs(result["cleanup_verified"], verified)
                self.assertEqual(result["state"], detail)
                self.assertFalse(self.service.book.check(secret)[0])
                self.assertEqual(len(result["revoked_grants"]), 1)
                self.assertIn("cleanup_finished_at", result)
                self.assertIn("cleanup_finished_at_monotonic", result)
                self.assertNotIn(
                    "private-cleanup-secret",
                    (lease_dir / "result.json").read_text(encoding="utf-8"),
                )

    def test_refused_lease_cleanup_always_publishes_safe_final_callback_observation(
        self,
    ):
        cases = (
            ("nonbool", ("yes", "private-cleanup-secret"), False, "cleanup_error"),
            (
                "object",
                (True, {"nested": SimpleNamespace(secret="private-cleanup-secret")}),
                False,
                "cleanup_error",
            ),
            (
                "exception-value",
                (True, RuntimeError("private-cleanup-secret")),
                False,
                "cleanup_error",
            ),
            ("raises", RuntimeError("private-cleanup-secret"), False, "cleanup_error"),
            (
                "json",
                (True, {"removed": ["owned"], "unknown": None}),
                True,
                {"removed": ["owned"], "unknown": None},
            ),
        )
        for name, callback_result, verified, detail in cases:
            with self.subTest(case=name):
                token = "refused-" + name
                lease_dir = self.state / "leases" / token
                lease_dir.mkdir(parents=True)
                # Valid owned identity, but no heartbeat: registration refuses
                # before dispatch and still must finish its cleanup journal.
                (lease_dir / "lease.json").write_text(
                    json.dumps(
                        {"token": token, "run_id": "run-one", "name": "exact-name"}
                    ),
                    encoding="utf-8",
                )
                errors = []
                options = (
                    {"side_effect": callback_result}
                    if isinstance(callback_result, Exception)
                    else {"return_value": callback_result}
                )
                with (
                    patch.object(self.service, "cleanup", **options),
                    patch("threading.excepthook", side_effect=errors.append),
                ):
                    self.service.tick()
                    result = _result(lease_dir)
                self.assertEqual(errors, [])
                self.assertEqual(result["reason"], "refused")
                self.assertTrue(result["revocation_verified"])
                self.assertIs(result["cleanup_verified"], verified)
                self.assertEqual(result["state"], detail)
                self.assertTrue((lease_dir / "refused.json").exists())
                self.assertFalse((lease_dir / "accepted.json").exists())
                self.assertFalse((lease_dir / "grant.secret").exists())
                self.assertNotIn(
                    "private-cleanup-secret",
                    (lease_dir / "result.json").read_text(encoding="utf-8"),
                )

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "service"
        self.cleanups = []

        def cleanup(identity):
            self.cleanups.append(
                (identity.name, identity.run_id, identity.token.get_secret_value())
            )
            return True, "removed_after_loss"

        self.service = LeaseService(
            self.state, loss_seconds=LOSS_SECONDS, cleanup=cleanup
        )
        self.addCleanup(self.service.server.server_close)
        self.addCleanup(wait_for_cleanup, self.service)

    def register(self, token="token-one"):
        lease_dir = self.state / "leases" / token
        lease_dir.mkdir(parents=True)
        (lease_dir / "heartbeat").write_text(repr(time.time()), encoding="utf-8")
        (lease_dir / "heartbeat.monotonic").write_text(
            repr(time.monotonic()), encoding="utf-8"
        )
        (lease_dir / "lease.json").write_text(
            json.dumps({"token": token, "run_id": "run-one", "name": "exact-name"}),
            encoding="utf-8",
        )
        self.service.tick()
        return lease_dir, (lease_dir / "grant.secret").read_text(encoding="utf-8")

    def test_heartbeat_replacement_keeps_old_value_readable_until_publish(self):
        heartbeat = self.state / "service.alive"
        heartbeat.write_text("1.0", encoding="utf-8")
        replace = os.replace
        seen_before_publish = []

        def inspect_replace(source, target):
            seen_before_publish.append(_owned_lease_service__read_float(heartbeat))
            self.assertEqual(Path(target), heartbeat)
            self.assertEqual(Path(source).parent, heartbeat.parent)
            replace(source, target)

        with patch(
            "laomedo.host.leases.service.os.replace", side_effect=inspect_replace
        ):
            _owned_lease_service__write_float(heartbeat, 2.0)
        self.assertEqual(seen_before_publish, [1.0])
        self.assertEqual(_owned_lease_service__read_float(heartbeat), 2.0)

    def test_heartbeat_retries_windows_replace_lock_and_cleans_pending_file(self):
        heartbeat = self.state / "service.alive"
        heartbeat.write_text("1.0", encoding="utf-8")
        replace = os.replace
        attempts = []

        def locked_once(source, target):
            attempts.append((source, target))
            if len(attempts) == 1:
                raise PermissionError("simulated reader lock")
            replace(source, target)

        with patch("laomedo.host.leases.service.os.replace", side_effect=locked_once):
            _owned_lease_service__write_float(heartbeat, 2.0)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(_owned_lease_service__read_float(heartbeat), 2.0)
        self.assertEqual(list(self.state.glob("service.alive.pending-*")), [])

    def test_failed_heartbeat_write_does_not_end_service_beat_loop(self):
        writes = []

        def fail_once(path, value):
            writes.append(path.name)
            if len(writes) == 1:
                raise PermissionError("simulated persistent lock")

        waits = []

        def stop_after_second_wait(seconds):
            waits.append(seconds)
            if len(waits) == 2:
                self.service.stopping.set()

        with (
            patch("laomedo.host.leases.service._write_float", side_effect=fail_once),
            patch.object(
                self.service.stopping, "wait", side_effect=stop_after_second_wait
            ),
            self.assertLogs(level="WARNING"),
        ):
            self.service._beat()
        self.assertEqual(
            writes, ["service.alive", "service.alive", "service.alive.monotonic"]
        )

    def test_heartbeat_read_retries_transient_windows_lock(self):
        heartbeat = self.state / "service.alive"
        heartbeat.write_text("2.0", encoding="utf-8")
        read_text = Path.read_text
        attempts = []

        def locked_once(path, *args, **kwargs):
            if path == heartbeat:
                attempts.append(path)
                if len(attempts) == 1:
                    raise PermissionError("simulated reader lock")
            return read_text(path, *args, **kwargs)

        with patch.object(Path, "read_text", autospec=True, side_effect=locked_once):
            self.assertEqual(_owned_lease_service__read_float(heartbeat), 2.0)
        self.assertEqual(len(attempts), 2)

    def test_json_read_retries_transient_windows_lock(self):
        record = self.state / "service.json"
        record.write_text('{"instance": "one"}', encoding="utf-8")
        read_text = Path.read_text
        attempts = []

        def locked_once(path, *args, **kwargs):
            if path == record:
                attempts.append(path)
                if len(attempts) == 1:
                    raise PermissionError("simulated reader lock")
            return read_text(path, *args, **kwargs)

        with patch.object(Path, "read_text", autospec=True, side_effect=locked_once):
            self.assertEqual(
                _owned_lease_service__read_json(record), {"instance": "one"}
            )
        self.assertEqual(len(attempts), 2)

    def test_serve_publishes_new_heartbeats_before_service_identity(self):
        (self.state / "service.json").write_text(
            json.dumps({"instance": "old-instance"}), encoding="utf-8"
        )
        (self.state / "service.alive").write_text("1.0", encoding="utf-8")
        (self.state / "service.alive.monotonic").write_text("1.0", encoding="utf-8")
        original_write = _owned_lease_service__write_json
        publication = []

        def inspect_publication(path, value):
            if path == self.state / "service.json":
                publication.append(
                    (
                        _owned_lease_service__read_json(path),
                        _owned_lease_service__read_float(self.state / "service.alive"),
                        _owned_lease_service__read_float(
                            self.state / "service.alive.monotonic"
                        ),
                        time.time(),
                        time.monotonic(),
                    )
                )
            original_write(path, value)

        with patch(
            "laomedo.host.leases.service._write_json", side_effect=inspect_publication
        ):
            thread = threading.Thread(target=self.service.serve, daemon=True)
            thread.start()
            try:
                deadline = time.monotonic() + 3
                while not publication and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertEqual(len(publication), 1)
                old_identity, wall, monotonic, now_wall, now_monotonic = publication[0]
                self.assertIsNone(old_identity)
                self.assertLess(now_wall - wall, 1)
                self.assertLess(now_monotonic - monotonic, 1)
            finally:
                self.service.stopping.set()
                thread.join(timeout=3)
            self.assertFalse(thread.is_alive())

    def test_serve_refuses_publication_when_initial_heartbeat_fails(self):
        with patch(
            "laomedo.host.leases.service._write_float",
            side_effect=OSError("unwritable heartbeat"),
        ):
            with self.assertRaisesRegex(OSError, "unwritable heartbeat"):
                self.service.serve()
        self.assertFalse((self.state / "service.json").exists())

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
        self.assertLessEqual(
            result["detected_at_monotonic"], result["revoked_at_monotonic"]
        )
        self.assertLessEqual(
            result["revoked_at_monotonic"], result["cleanup_finished_at_monotonic"]
        )
        self.assertEqual(self.cleanups, [("exact-name", "run-one", "token-one")])
        self.assertEqual(self.service.book.check(secret)[0], False)
        self.service.tick()  # a finished lease is never processed twice
        self.assertEqual(len(self.cleanups), 1)

    def test_monotonic_stale_heartbeat_revokes_even_if_wall_clock_is_fresh(self):
        lease_dir, secret = self.register()
        (lease_dir / "heartbeat.monotonic").write_text(
            repr(time.monotonic() - 10), encoding="utf-8"
        )
        self.service.tick()
        result = _result(lease_dir)
        self.assertEqual(result["reason"], "heartbeat_lost")
        self.assertFalse(self.service.book.check(secret)[0])

    def test_fresh_heartbeat_renews_and_unrenewed_grant_expires(self):
        lease_dir, secret = self.register()
        self.service.tick()
        self.assertTrue(self.service.book.check(secret)[0])
        for grant in self.service.book.by_digest.values():
            grant.expires_at = time.time() - 1  # simulate a missed renewal window
        self.assertFalse(self.service.book.check(secret)[0])

    def test_done_revokes_grant_and_checks_absence(self):
        lease_dir, secret = self.register()
        (lease_dir / "done").write_text("done", encoding="utf-8")
        with patch(
            "laomedo.host.leases.service.inspect_exact", return_value=("absent", None)
        ):
            self.service.tick()
            result = _result(lease_dir)
        self.assertEqual((result["reason"], result["cleanup_verified"]), ("done", True))
        self.assertFalse(self.service.book.check(secret)[0])
        self.assertEqual(self.cleanups, [])

    def test_malformed_lease_is_ignored(self):
        lease_dir = self.state / "leases" / "token-two"
        lease_dir.mkdir(parents=True)
        (lease_dir / "lease.json").write_text(
            json.dumps({"token": "other", "run_id": "run", "name": "n"}),
            encoding="utf-8",
        )
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
            req = request.Request(
                url,
                data=b"{}",
                method="POST",
                headers={"Authorization": "Bearer " + token},
            )
            try:
                with request.urlopen(req, timeout=5) as response:
                    return response.status
            except error.HTTPError as exc:
                return exc.code

        self.assertEqual(write(secret), 200)
        (lease_dir / "heartbeat").write_text(repr(time.time() - 10), encoding="utf-8")
        self.service.tick()
        self.assertEqual(write(secret), 403)
        events = [
            json.loads(line)
            for line in (self.state / "grant-events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertEqual([event["accepted"] for event in events], [True, False])


class LeaseClientTests(unittest.TestCase):
    def test_unverified_owner_stops_heartbeats_without_signalling_done(self):
        from unittest.mock import Mock

        client = object.__new__(LeaseClient)
        client.stop_event = threading.Event()
        client.thread = Mock()
        client.dir = Path(self.temp.name) / "unverified-lease"
        client.dir.mkdir()
        client.stop_heartbeats()
        self.assertTrue(client.stop_event.is_set())
        self.assertFalse((client.dir / "done").exists())
        client.thread.join.assert_called_once_with(timeout=3)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "service"

    def wait_for_service(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if (
                _owned_lease_service__read_json(self.state / "service.json") is not None
                and _owned_lease_service__read_float(self.state / "service.alive")
                is not None
                and _owned_lease_service__read_float(
                    self.state / "service.alive.monotonic"
                )
                is not None
            ):
                return
            time.sleep(0.05)
        self.fail("lease service did not publish complete readiness")

    def test_client_refuses_missing_or_stale_service(self):
        with self.assertRaisesRegex(RuntimeError, "lease_service_unavailable"):
            LeaseClient(
                self.state,
                docker_endpoint="unix:///unit-test.sock",
                run_id="r",
                name="n",
                token="t",
                cancelled=threading.Event(),
            )
        self.state.mkdir(parents=True)
        (self.state / "service.json").write_text(
            json.dumps({"pid": -1, "port": 1, "instance": "i"}), encoding="utf-8"
        )
        (self.state / "service.alive").write_text(
            repr(time.time() - 60), encoding="utf-8"
        )
        with self.assertRaisesRegex(RuntimeError, "lease_service_unavailable"):
            LeaseClient(
                self.state,
                docker_endpoint="unix:///unit-test.sock",
                run_id="r",
                name="n",
                token="t",
                cancelled=threading.Event(),
            )

    def test_client_registers_heartbeats_and_finishes_with_live_service(self):
        service = LeaseService(self.state, loss_seconds=5)
        runner = threading.Thread(target=service.serve, daemon=True)
        runner.start()
        self.addCleanup(service.stopping.set)
        self.wait_for_service()
        cancelled = threading.Event()
        # The service runs in-thread here; production refuses a same-process service.
        with patch("laomedo.host.leases.service.os.getpid", return_value=-2):
            client = LeaseClient(
                self.state,
                docker_endpoint="unix:///unit-test.sock",
                run_id="run-one",
                name="exact-name",
                token="token-one",
                cancelled=cancelled,
            )
        self.assertTrue(client.grant_id.startswith("grant-"))
        self.assertTrue(service.book.check(client.grant_secret())[0])
        with patch(
            "laomedo.host.leases.service.inspect_exact", return_value=("absent", None)
        ):
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
        self.wait_for_service()

        original_write = _owned_lease_service__write_json
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

        with (
            patch("laomedo.host.leases.client._write_json", side_effect=checked_write),
            patch("laomedo.host.leases.service.os.getpid", return_value=-2),
        ):
            client = LeaseClient(
                self.state,
                docker_endpoint="unix:///unit-test.sock",
                run_id="run-race",
                name="exact-name",
                token="token-race",
                cancelled=threading.Event(),
            )
        self.assertEqual(saw_staged_registration, [True])
        self.assertFalse((client.dir / "result.json").exists())
        self.assertTrue((client.dir / "accepted.json").exists())
        with patch(
            "laomedo.host.leases.service.inspect_exact", return_value=("absent", None)
        ):
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
        self.wait_for_service()
        try:
            with patch("laomedo.host.leases.service.os.getpid", return_value=-2):
                with self.assertRaisesRegex(
                    RuntimeError, "lease_service_refused:mediated_lease_not_authorized"
                ):
                    LeaseClient(
                        self.state,
                        docker_endpoint="unix:///unit-test.sock",
                        run_id="r",
                        name="n",
                        token="t",
                        cancelled=threading.Event(),
                        mediation_request={
                            "invocation_id": "i",
                            "repository": "example/disposable",
                            "branch": "probe-r",
                        },
                    )
            self.assertTrue(cleanup_started.wait(2))
            self.assertFalse((self.state / "leases" / "t" / "result.json").exists())
        finally:
            release_cleanup.set()


if __name__ == "__main__":
    unittest.main()
