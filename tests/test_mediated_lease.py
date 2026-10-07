"""Credential-free checks of the durable mediator/lease bridge."""

import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from urllib import error, request

from laomedo.github_mediation import MediationError, MediationStore
from laomedo.lease_service import GRANT_TTL_SECONDS, LOSS_SECONDS, LeaseService
from laomedo.mediation_authority import RunGrantAuthority
from laomedo.mediation_service import MediationHTTPService


def _result(directory: Path) -> dict:
    path = directory / "result.json"
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        time.sleep(.01)
    raise AssertionError("lease result not written")


class MediatedLeaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = self.root / "service"
        self.generations = {}
        self.repositories = {"connection-a": "example/disposable",
                             "connection-b": "example/disposable"}
        self.store = MediationStore(
            self.root / "private" / "mediator.sqlite",
            connection_is_current=lambda identity, generation, repository:
                self.generations.get(identity) == generation and
                self.repositories.get(identity) == repository)
        self.authority = RunGrantAuthority(
            self.root / "private" / "authority.sqlite",
            connection_authorizer=lambda identity, generation, repository, operator:
                operator == "test-operator" and
                self.generations.get(identity) == generation and
                self.repositories.get(identity) == repository)
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

    def register(self, run_id, lease_token, *, operations=None, target_prs=None,
                 connection_id=None, connection_generation=None, authority=None):
        approver = authority or self.authority
        reference = approver.approve(
            invocation_id="invocation-" + run_id, repository="example/disposable",
            branch="branch-" + run_id,
            operations=operations or {"git_push", "pr_create", "actions_read"},
            target_prs=target_prs, reviewed_by="test-operator",
            connection_id=connection_id,
            connection_generation=connection_generation)
        approver.bind_run(reference, run_id)
        directory = self.state / "leases" / lease_token
        directory.mkdir(parents=True)
        (directory / "heartbeat").write_text(repr(time.time()), encoding="utf-8")
        (directory / "heartbeat.monotonic").write_text(
            repr(time.monotonic()), encoding="utf-8")
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
        result = _result(first)
        self.assertEqual(result["reason"], "heartbeat_lost")
        self.assertEqual(result["revoked_grants"], [accepted["grant_id"]])
        self.assertLessEqual(result["revoked_at"], result["cleanup_finished_at"])
        self.assertLessEqual(result["detected_at_monotonic"],
                             result["revoked_at_monotonic"])
        self.assertLessEqual(result["revoked_at_monotonic"],
                             result["cleanup_finished_at_monotonic"])
        with self.assertRaisesRegex(MediationError, "grant_unavailable"):
            self.read(token_a)
        self.read(token_b)
        self.assertEqual(self.cleanups, [("container-a", "a", "lease-a")])

    def test_slow_cleanup_does_not_block_other_run_or_admission(self):
        self.assertLess(GRANT_TTL_SECONDS + LOSS_SECONDS, 60)
        first, _, token_a = self.register("a", "lease-a")
        _, _, token_b = self.register("b", "lease-b")
        started = threading.Event()
        release = threading.Event()

        def slow_cleanup(name, run_id, lease_token):
            started.set()
            if not release.wait(3):
                raise AssertionError("cleanup not released")
            return self.cleanup(name, run_id, lease_token)

        self.service.cleanup = slow_cleanup
        (first / "heartbeat").write_text(repr(time.time() - 10), encoding="utf-8")
        try:
            start = time.monotonic()
            self.service.tick()
            self.assertLess(time.monotonic() - start, 1)
            self.assertTrue(started.wait(1))
            self.assertTrue((first / "revoked.json").exists())
            with self.assertRaisesRegex(MediationError, "grant_unavailable"):
                self.read(token_a)
            self.read(token_b)
            # A new run must be admitted while A's Docker cleanup is held.
            _, _, token_c = self.register("c", "lease-c")
            self.read(token_c)
            self.service.tick()
            self.read(token_b)
            self.assertFalse((first / "result.json").exists())
        finally:
            release.set()
        self.assertEqual(_result(first)["reason"], "heartbeat_lost")

    def test_scan_rechecks_time_after_an_earlier_lease_stalls(self):
        self.register("a", "a-lease")
        second, _, token_b = self.register("b", "b-lease")
        original = self.service._tick_lease

        def delayed_first(directory, now):
            if directory.name == "a-lease":
                time.sleep(.6)
            return original(directory, now)

        self.service._tick_lease = delayed_first
        (second / "heartbeat").write_text(repr(time.time() - .1), encoding="utf-8")
        self.service.tick()
        self.assertEqual(_result(second)["reason"], "heartbeat_lost")
        with self.assertRaisesRegex(MediationError, "grant_unavailable"):
            self.read(token_b)

    def test_trusted_approval_can_authorize_same_repository_read(self):
        with self.assertRaisesRegex(MediationError, "authorization_invalid"):
            self.authority.approve(
                invocation_id="denied-default", repository="example/disposable",
                branch="branch-read", operations={"api_rest_read"},
                reviewed_by="test-operator")
        diagnostic = RunGrantAuthority(
            self.root / "private" / "authority.sqlite",
            diagnostic_repository_read=True)
        _, _, bearer = self.register("read", "lease-read", operations={"api_rest_read"},
                                      authority=diagnostic)
        result = self.store.invoke(
            token=bearer, repository="example/disposable", operation="api_rest_read",
            payload={"method": "GET", "path": "/repos/example/disposable/branches/main"},
            effect_id=None, transport=self.transport)
        self.assertEqual(result["state"], "confirmed")
        self.assertEqual(len(self.calls), 1)

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
        result = _result(directory)
        self.assertEqual(result["reason"], "service_restart")
        self.assertEqual(result["revoked_grants"], [accepted["grant_id"]])
        self.assertEqual(self.cleanups, [("container-a", "a", "lease-a")])
        self.assertFalse(restarted.mediator.renew_lease(
            run_id="a", lease_token="lease-a", lease_scope=str(self.state), ttl_seconds=60))

    def test_incomplete_mediation_request_never_acknowledges(self):
        directory = self.state / "leases" / "lease-a"
        directory.mkdir(parents=True)
        (directory / "heartbeat").write_text(repr(time.time()), encoding="utf-8")
        (directory / "heartbeat.monotonic").write_text(
            repr(time.monotonic()), encoding="utf-8")
        (directory / "lease.json").write_text(json.dumps({
            "token": "lease-a", "run_id": "a", "name": "container-a"}), encoding="utf-8")
        self.service.tick()
        result = _result(directory)
        self.assertEqual((result["reason"], result["error_code"]),
                         ("refused", "mediated_lease_request_invalid"))
        self.assertFalse((directory / "accepted.json").exists())
        self.assertFalse((directory / "grant.secret").exists())

    def test_runner_request_cannot_authorize_itself(self):
        self.service.mediation_authority = None
        directory = self.state / "leases" / "lease-a"
        directory.mkdir(parents=True)
        (directory / "heartbeat").write_text(repr(time.time()), encoding="utf-8")
        (directory / "heartbeat.monotonic").write_text(
            repr(time.monotonic()), encoding="utf-8")
        (directory / "lease.json").write_text(json.dumps({
            "token": "lease-a", "run_id": "a", "name": "container-a",
            "mediation": {"invocation_id": "invocation-a",
                          "repository": "example/disposable", "branch": "branch-a"}
        }), encoding="utf-8")
        self.service.tick()
        result = _result(directory)
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
        self.assertEqual(_result(bad)["reason"], "refused")
        self.assertEqual(_result(good)["reason"],
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
        with request.urlopen(f"http://127.0.0.1:{mediator.port}/v1/health",
                             timeout=5) as response:
            self.assertEqual(json.load(response),
                             {"status": "ready", "instance": mediator.instance})
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
        (directory / "heartbeat").write_text(repr(time.time()), encoding="utf-8")
        (directory / "heartbeat.monotonic").write_text(
            repr(time.monotonic()), encoding="utf-8")
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

    def test_connection_generation_blocks_old_active_run_without_harming_other(self):
        self.generations.update({"connection-a": 1, "connection-b": 1})
        _, _, token_a = self.register("a", "lease-a", operations={"actions_read"},
            connection_id="connection-a", connection_generation=1)
        _, _, token_b = self.register("b", "lease-b", operations={"actions_read"},
            connection_id="connection-b", connection_generation=1)
        routed = []

        def selected_transport(repository, operation, payload, *, connection_id,
                               connection_generation):
            routed.append((connection_id, connection_generation))
            return {"ok": True}

        def use(token):
            return self.store.invoke(token=token, repository="example/disposable",
                operation="actions_read", payload={}, effect_id=None,
                transport=selected_transport)

        self.assertEqual(use(token_a)["state"], "confirmed")
        self.generations["connection-a"] = 2
        with self.assertRaisesRegex(MediationError, "connection_unavailable"):
            use(token_a)
        self.assertEqual(routed, [("connection-a", 1)])
        self.assertEqual(use(token_b)["state"], "confirmed")
        self.assertEqual(routed[-1], ("connection-b", 1))
        _, _, token_new = self.register("c", "lease-c", operations={"actions_read"},
            connection_id="connection-a", connection_generation=2)
        self.assertEqual(use(token_new)["state"], "confirmed")
        self.assertEqual(routed[-1], ("connection-a", 2))

    def test_connection_bound_grant_fails_closed_without_resolver(self):
        independent = MediationStore(self.root / "private" / "no-resolver.sqlite")
        with self.assertRaisesRegex(MediationError, "connection_unavailable"):
            independent.issue(run_id="a", invocation_id="invocation-a",
                repository="example/disposable", operations={"actions_read"},
                ttl_seconds=60, connection_id="connection-a",
                connection_generation=1)

    def test_connection_approval_fails_closed_on_wrong_repository_or_missing_resolver(self):
        self.generations["connection-a"] = 1
        no_resolver = RunGrantAuthority(self.root / "private" / "no-connection.sqlite")
        with self.assertRaisesRegex(MediationError, "connection_unavailable"):
            no_resolver.approve(invocation_id="invocation-a",
                repository="example/disposable", branch="branch-a",
                operations={"actions_read"}, reviewed_by="test-operator",
                connection_id="connection-a", connection_generation=1)
        with self.assertRaisesRegex(MediationError, "connection_unavailable"):
            self.authority.approve(invocation_id="invocation-a",
                repository="other/repo", branch="branch-a",
                operations={"actions_read"}, reviewed_by="test-operator",
                connection_id="connection-a", connection_generation=1)


if __name__ == "__main__":
    unittest.main()
