"""Credential-free checks of the durable mediator/lease bridge."""

import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from urllib import error, request

from laomedo.github_mediation import MediationError, MediationStore
from laomedo.lease_service import LeaseService
from laomedo.mediation_authority import RunGrantAuthority
from laomedo.mediation_service import MediationHTTPService


class MediatedLeaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = self.root / "service"
        self.store = MediationStore(self.root / "private" / "mediator.sqlite")
        self.authority = RunGrantAuthority(self.root / "private" / "authority.sqlite")
        self.cleanups = []

        def cleanup(name, run_id, token):
            self.cleanups.append((name, run_id, token))
            return True, "removed_after_loss"

        self.cleanup = cleanup
        self.authorize = self.authority.authorize_lease
        self.calls = []

        def transport(repository, operation, payload):
            self.calls.append((repository, operation, payload))
            return {"ok": True}

        self.service = LeaseService(self.state, mediator=self.store,
                                    cleanup=cleanup, loss_seconds=.5,
                                    mediation_authority=self.authorize)
        self.transport = transport
        self.addCleanup(self.service.server.server_close)

    def register(self, run_id, lease_token, *, operations=None, target_prs=None):
        reference = self.authority.approve(
            invocation_id="invocation-" + run_id, repository="example/disposable",
            branch="branch-" + run_id,
            operations=operations or {"git_push", "pr_create", "actions_read"},
            target_prs=target_prs, reviewed_by="test-operator")
        self.authority.bind_run(reference, run_id)
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
        self.service.tick()
        result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
        self.assertEqual((result["reason"], result["error_code"]),
                         ("refused", "mediated_lease_request_invalid"))
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
        self.service.tick()
        result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
        self.assertEqual((result["reason"], result["error_code"]),
                         ("refused", "mediated_lease_not_authorized"))
        self.assertFalse((directory / "accepted.json").exists())

    def test_bad_lease_does_not_starve_good_cleanup(self):
        bad = self.state / "leases" / "a-bad"
        bad.mkdir(parents=True)
        (bad / "lease.json").write_text(json.dumps({
            "token": "a-bad", "run_id": "bad", "name": "bad-container"}), encoding="utf-8")
        good, _, token = self.register("good", "z-good")
        (good / "heartbeat").write_text(repr(time.time() - 10), encoding="utf-8")
        self.service.tick()
        self.assertEqual(json.loads((bad / "result.json").read_text())["reason"], "refused")
        self.assertEqual(json.loads((good / "result.json").read_text())["reason"],
                         "heartbeat_lost")
        with self.assertRaisesRegex(MediationError, "grant_unavailable"):
            self.read(token)

    def test_authority_rejects_changed_scope_and_second_run_or_lease(self):
        ref = self.authority.approve(
            invocation_id="invocation-a", repository="example/disposable",
            branch="branch-a", operations={"actions_read"}, reviewed_by="operator")
        scope = self.authority.bind_run(ref, "a")
        with self.assertRaisesRegex(MediationError, "authorization_unavailable"):
            self.authority.bind_run(ref, "b")
        self.assertIsNone(self.authority.authorize_lease(
            {"run_id": "a", "token": "lease-a"},
            {**scope, "repository": "other/repo"}))
        self.assertEqual(self.authority.authorize_lease(
            {"run_id": "a", "token": "lease-a"}, scope)["operations"], {"actions_read"})
        self.assertIsNone(self.authority.authorize_lease(
            {"run_id": "a", "token": "lease-b"}, scope))

    def test_service_issues_only_trusted_pr_target(self):
        _, _, token = self.register("a", "lease-a", operations={"pr_update"},
                                    target_prs={7: "main"})
        payload = {"number": 999, "head": "branch-a", "base": "main", "marker": "m"}
        with self.assertRaisesRegex(MediationError, "target_pr_denied"):
            self.store.invoke(token=token, repository="example/disposable",
                              operation="pr_update", payload=payload,
                              effect_id="wrong-pr", transport=lambda *_: self.calls.append("bad"))
        self.assertEqual(self.calls, [])
        payload["number"] = 7
        result = self.store.invoke(token=token, repository="example/disposable",
                                   operation="pr_update", payload=payload,
                                   effect_id="approved-pr", transport=lambda *_: {"ok": True})
        self.assertEqual(result["state"], "confirmed")

    def test_lease_service_failure_still_expires_at_use(self):
        _, _, token_a = self.register("a", "lease-a")
        _, _, token_b = self.register("b", "lease-b")
        self.service.server.server_close()  # no revoke and no replacement service
        # The independent mediator remains available, but refuses both grants
        # once the last lease renewal's maximum TTL has elapsed.
        expired_view = MediationStore(self.store.path, now=lambda: time.time() + 61)
        mediator = MediationHTTPService(expired_view, self.transport)
        import threading
        thread = threading.Thread(target=mediator.serve, daemon=True)
        thread.start()
        self.addCleanup(mediator.close)
        for token in (token_a, token_b):
            call = request.Request(
                f"http://127.0.0.1:{mediator.port}/v1/mediate",
                data=json.dumps({"repository": "example/disposable",
                                 "operation": "actions_read", "payload": {}}).encode(),
                method="POST", headers={"Authorization": "Bearer " + token})
            with self.assertRaises(error.HTTPError) as denial:
                request.urlopen(call, timeout=5)
            self.assertEqual(denial.exception.code, 403)
        self.assertEqual(self.calls, [])

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
        reference = self.authority.approve(
            invocation_id="invocation-a", repository="example/disposable",
            branch="branch-a", operations={"git_push"}, reviewed_by="test-operator")
        self.authority.bind_run(reference, "a")
        with self.assertRaises(OSError):
            self.service._accept(directory, json.loads(
                (directory / "lease.json").read_text(encoding="utf-8")), time.time())
        self.assertFalse((directory / "accepted.json").is_file())
        with closing(sqlite3.connect(self.store.path)) as db:
            grants = db.execute("SELECT revoked_at FROM grants").fetchall()
        self.assertEqual(len(grants), 1)
        self.assertIsNotNone(grants[0][0])

    def test_http_mediator_denies_revoked_grant_before_transport(self):
        first, _, token_a = self.register("a", "lease-a")
        _, _, token_b = self.register("b", "lease-b")
        import threading
        mediator = MediationHTTPService(self.store, self.transport)
        thread = threading.Thread(target=mediator.serve, daemon=True)
        thread.start()
        self.addCleanup(mediator.close)

        def mediate(token):
            body = json.dumps({"repository": "example/disposable",
                               "operation": "actions_read", "payload": {}}).encode()
            call = request.Request(
                f"http://127.0.0.1:{mediator.port}/v1/mediate",
                data=body, method="POST", headers={
                    "Authorization": "Bearer " + token, "Content-Type": "application/json"})
            try:
                with request.urlopen(call, timeout=5) as response:
                    return response.status
            except error.HTTPError as failure:
                return failure.code

        self.assertEqual(mediate(token_a), 200)
        (first / "heartbeat").write_text(repr(time.time() - 10), encoding="utf-8")
        self.service.tick()
        before = len(self.calls)
        self.assertEqual(mediate(token_a), 403)
        self.assertEqual(len(self.calls), before)
        self.assertEqual(mediate(token_b), 200)


if __name__ == "__main__":
    unittest.main()
