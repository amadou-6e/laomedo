"""Credential-free checks of the durable mediator/lease bridge."""

import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from laomedo.github_mediation import MediationError, MediationStore
from laomedo.lease_service import LeaseService


class MediatedLeaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = self.root / "service"
        self.store = MediationStore(self.root / "private" / "mediator.sqlite")
        self.cleanups = []

        def cleanup(name, run_id, token):
            self.cleanups.append((name, run_id, token))
            return True, "removed_after_loss"

        self.cleanup = cleanup
        self.authorize = lambda lease, request: (
            request["invocation_id"] == "invocation-" + lease["run_id"] and
            request["repository"] == "example/disposable" and
            request["branch"] == "branch-" + lease["run_id"])
        self.service = LeaseService(self.state, mediator=self.store,
                                    cleanup=cleanup, loss_seconds=.5,
                                    mediation_authority=self.authorize)
        self.addCleanup(self.service.server.server_close)
        self.calls = []

    def register(self, run_id, lease_token):
        directory = self.state / "leases" / lease_token
        directory.mkdir(parents=True)
        (directory / "heartbeat").write_text(repr(time.time()), encoding="utf-8")
        (directory / "lease.json").write_text(json.dumps({
            "token": lease_token, "run_id": run_id, "name": "container-" + run_id,
            "mediation": {"invocation_id": "invocation-" + run_id,
                          "repository": "example/disposable", "branch": "branch-" + run_id}
        }), encoding="utf-8")
        self.service.tick()
        accepted = json.loads((directory / "accepted.json").read_text(encoding="utf-8"))
        secret = (directory / "grant.secret").read_text(encoding="utf-8")
        return directory, accepted, secret

    def read(self, token):
        return self.store.invoke(
            token=token, repository="example/disposable", operation="actions_read",
            payload={}, effect_id=None, transport=lambda *args: self.calls.append(args) or {})

    def test_exact_run_revoke_precedes_cleanup_and_other_run_survives(self):
        first, accepted, token_a = self.register("a", "lease-a")
        _, _, token_b = self.register("b", "lease-b")
        self.assertTrue(accepted["grant_id"])
        self.read(token_a)
        self.read(token_b)
        self.assertNotIn(token_a, self.store.path.read_bytes().decode("latin1"))

        def cleanup_after_denial(name, run_id, lease_token):
            with self.assertRaisesRegex(MediationError, "grant_unavailable"):
                self.read(token_a)
            return self.cleanup(name, run_id, lease_token)

        self.service.cleanup = cleanup_after_denial

        (first / "heartbeat").write_text(repr(time.time() - 10), encoding="utf-8")
        self.service.tick()
        result = json.loads((first / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["reason"], "heartbeat_lost")
        self.assertEqual(result["revoked_grants"], [accepted["grant_id"]])
        self.assertLessEqual(result["revoked_at"], result["cleanup_finished_at"])
        with self.assertRaisesRegex(MediationError, "grant_unavailable"):
            self.read(token_a)
        self.read(token_b)
        self.assertEqual(self.cleanups, [("container-a", "a", "lease-a")])

    def test_reopened_service_revokes_old_grant_and_never_reissues_it(self):
        directory, accepted, token = self.register("a", "lease-a")
        self.service.server.server_close()
        restarted = LeaseService(self.state, mediator=MediationStore(self.store.path),
                                 cleanup=self.cleanup,
                                 mediation_authority=self.authorize)
        self.addCleanup(restarted.server.server_close)
        with self.assertRaisesRegex(MediationError, "grant_unavailable"):
            self.read(token)
        restarted.tick()
        result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["reason"], "service_restart")
        self.assertEqual(result["revoked_grants"], [accepted["grant_id"]])
        self.assertEqual(self.cleanups, [("container-a", "a", "lease-a")])
        self.assertFalse(restarted.mediator.renew_lease(
            run_id="a", lease_token="lease-a", lease_scope=str(self.state), ttl_seconds=60))

    def test_incomplete_mediation_request_never_acknowledges(self):
        directory = self.state / "leases" / "lease-a"
        directory.mkdir(parents=True)
        (directory / "lease.json").write_text(json.dumps({
            "token": "lease-a", "run_id": "a", "name": "container-a"}), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "mediated_lease_request_invalid"):
            self.service.tick()
        self.assertFalse((directory / "accepted.json").exists())
        self.assertFalse((directory / "grant.secret").exists())

    def test_runner_request_cannot_authorize_itself(self):
        self.service.mediation_authority = None
        directory = self.state / "leases" / "lease-a"
        directory.mkdir(parents=True)
        (directory / "lease.json").write_text(json.dumps({
            "token": "lease-a", "run_id": "a", "name": "container-a",
            "mediation": {"invocation_id": "invocation-a",
                          "repository": "example/disposable", "branch": "branch-a"}
        }), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "mediated_lease_not_authorized"):
            self.service.tick()
        self.assertFalse((directory / "accepted.json").exists())

    def test_acknowledgement_write_failure_revokes_issued_grant(self):
        directory = self.state / "leases" / "lease-a"
        directory.mkdir(parents=True)
        (directory / "lease.json").write_text(json.dumps({
            "token": "lease-a", "run_id": "a", "name": "container-a",
            "mediation": {"invocation_id": "invocation-a",
                          "repository": "example/disposable", "branch": "branch-a"}
        }), encoding="utf-8")
        # Make the acknowledgement path a directory. Grant issuance succeeds,
        # but no dispatch acknowledgement can be durably written.
        (directory / "accepted.json").mkdir()
        with self.assertRaises(OSError):
            self.service._accept(directory, json.loads(
                (directory / "lease.json").read_text(encoding="utf-8")), time.time())
        self.assertFalse((directory / "accepted.json").is_file())
        with closing(sqlite3.connect(self.store.path)) as db:
            grants = db.execute("SELECT revoked_at FROM grants").fetchall()
        self.assertEqual(len(grants), 1)
        self.assertIsNotNone(grants[0][0])


if __name__ == "__main__":
    unittest.main()
