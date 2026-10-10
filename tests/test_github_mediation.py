"""Zero-credential checks of the durable mediated-write boundary."""

from pathlib import Path
from contextlib import closing
from types import SimpleNamespace
import sqlite3
import tempfile
import threading
import time
import unittest

from laomedo.github_mediation import KnownRejected, MediationError, MediationStore


REPO = "example/disposable"


class MediationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="laomedo-mediation-")
        self.addCleanup(self.tmp.cleanup)
        self.clock = [1000.0]
        self.path = Path(self.tmp.name) / "mediator.db"
        self.workflow_changes = set()
        self.store = MediationStore(
            self.path, now=lambda: self.clock[0],
            workflow_change_classifier=lambda repo, branch, commit:
                commit in self.workflow_changes)
        self.calls = []

    def grant(self, run="run-a", operations=None, branch="run-a-branch", issues=None,
              target_prs=None):
        return self.store.issue(run_id=run, invocation_id=run + "-invocation",
                                repository=REPO,
                                operations=operations or {"git_push", "pr_create", "pr_list"},
                                branch=branch, reviewed_issue_requests=issues,
                                target_prs=target_prs, ttl_seconds=60)

    def transport(self, repository, operation, payload):
        self.calls.append((repository, operation, payload))
        return {"number": len(self.calls), "operation": operation}

    def invoke(self, token, operation, payload=None, effect_id=None, repository=REPO,
               transport=None):
        return self.store.invoke(token=token, repository=repository, operation=operation,
                                 payload=payload or {}, effect_id=effect_id,
                                 transport=transport or self.transport)

    def assert_code(self, code, function):
        with self.assertRaises(MediationError) as found:
            function()
        self.assertEqual(found.exception.code, code)

    def test_confirmed_repeat_and_request_conflict(self):
        grant_id, token = self.grant()
        self.assertNotIn(token, self.path.read_bytes().decode("latin1"))
        self.assertTrue(grant_id)
        payload = {"branch": "run-a-branch", "commit": "a" * 40}
        first = self.invoke(token, "git_push", payload, "effect-1")
        repeat = self.invoke(token, "git_push", payload, "effect-1")
        self.assertEqual(first["state"], "confirmed")
        self.assertEqual(first["result"], repeat["result"])
        self.assertFalse(repeat["resent"])
        self.assertEqual(len(self.calls), 1)
        self.assert_code("effect_conflict", lambda: self.invoke(
            token, "git_push", {"branch": "run-a-branch", "commit": "b" * 40}, "effect-1"))
        self.assertEqual(len(self.calls), 1)

    def test_create_cannot_choose_an_unapproved_base(self):
        _, token = self.grant()
        payload = {'head': 'run-a-branch', 'base': 'other-base', 'title': 'T',
                   'body': 'marker body', 'marker': 'marker'}
        self.assert_code('pr_base_denied', lambda: self.invoke(
            token, 'pr_create', payload, 'wrong-base'))
        self.assertEqual(self.calls, [])

    def test_legacy_effect_table_adds_attribution_without_rewriting_history(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DROP TABLE effects")
            db.execute("""CREATE TABLE effects (
                run_id TEXT NOT NULL, effect_id TEXT NOT NULL,
                request_hash TEXT NOT NULL, repository TEXT NOT NULL,
                operation TEXT NOT NULL, target_key TEXT NOT NULL,
                state TEXT NOT NULL, result_json TEXT, error_code TEXT,
                PRIMARY KEY(run_id,effect_id))""")
            db.execute("INSERT INTO effects VALUES (?,?,?,?,?,?,?,?,?)",
                       ("historic", "old", "hash", REPO, "pr_create", "target",
                        "unknown", None, None))
        reopened = MediationStore(self.path, now=lambda: self.clock[0])
        _, token = reopened.issue(
            run_id="new", invocation_id="new-invocation", repository=REPO,
            operations={"pr_create"}, branch="new-branch", ttl_seconds=60,
            approval_identity="test-operator")
        result = reopened.invoke(
            token=token, repository=REPO, operation="pr_create",
            payload={"head": "new-branch", "base": "main", "marker": "new"},
            effect_id="new", transport=self.transport)
        self.assertEqual(result["state"], "confirmed")
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute(
                "SELECT run_id,grant_id,invocation_id,approval_identity FROM effects "
                "ORDER BY run_id").fetchall()
        self.assertEqual(rows[0], ("historic", None, None, None))
        self.assertEqual(rows[1][0], "new")
        self.assertEqual(rows[1][2:], ("new-invocation", "test-operator"))
        self.assertTrue(rows[1][1])

    def test_slow_workflow_classification_does_not_lock_lease_renewal(self):
        started = threading.Event()
        release = threading.Event()

        def classify(*_):
            started.set()
            if not release.wait(3):
                raise AssertionError("classification not released")
            return False

        store = MediationStore(self.path, now=lambda: self.clock[0],
                               workflow_change_classifier=classify)
        _, token = store.issue(
            run_id="slow", invocation_id="invocation-slow", repository=REPO,
            branch="slow-branch", operations={"git_push"}, ttl_seconds=50,
            lease_token="lease-slow", lease_scope="service", service_instance="one")
        outcome = []

        def push():
            try:
                outcome.append(store.invoke(
                    token=token, repository=REPO, operation="git_push",
                    payload={"branch": "slow-branch", "commit": "a" * 40},
                    effect_id="slow-effect", transport=self.transport))
            except Exception as failure:
                outcome.append(failure)

        worker = threading.Thread(target=push)
        worker.start()
        try:
            self.assertTrue(started.wait(1))
            began = time.monotonic()
            self.assertTrue(store.renew_lease(
                run_id="slow", lease_token="lease-slow",
                lease_scope="service", ttl_seconds=50))
            self.assertLess(time.monotonic() - began, 1)
        finally:
            release.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(outcome[0]["state"], "confirmed")

    def test_lease_expiry_cannot_extend_past_last_heartbeat_cap(self):
        store = MediationStore(self.path, now=lambda: self.clock[0])
        _, token = store.issue(
            run_id="bounded", invocation_id="invocation-bounded", repository=REPO,
            operations={"pr_list"}, ttl_seconds=50,
            lease_token="lease-bounded", lease_scope="service",
            service_instance="one", expires_not_after=1005)
        self.clock[0] = 1004
        self.assertTrue(store.renew_lease(
            run_id="bounded", lease_token="lease-bounded",
            lease_scope="service", ttl_seconds=50,
            expires_not_after=1005))
        self.clock[0] = 1006
        self.assert_code("grant_unavailable", lambda: store.invoke(
            token=token, repository=REPO, operation="pr_list", payload={},
            effect_id=None, transport=self.transport))
        self.assertFalse(store.renew_lease(
            run_id="bounded", lease_token="lease-bounded",
            lease_scope="service", ttl_seconds=50,
            expires_not_after=1005))

    def test_lost_response_survives_reopen_without_resend(self):
        _, token = self.grant()
        payload = {"head": "run-a-branch", "base": "main", "marker": "request-1"}

        def accepted_then_lost(repository, operation, body):
            self.calls.append((repository, operation, body))
            raise ConnectionError("response lost after remote acceptance")

        first = self.invoke(token, "pr_create", payload, "effect-1",
                            transport=accepted_then_lost)
        self.assertEqual(first["state"], "unknown")
        reopened = MediationStore(self.path, now=lambda: self.clock[0])
        repeated = reopened.invoke(token=token, repository=REPO, operation="pr_create",
                                   payload=payload, effect_id="effect-1",
                                   transport=accepted_then_lost)
        self.assertEqual(repeated, {"state": "unknown", "resent": False})
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(reopened.effect("run-a", "effect-1")["state"], "unknown")

    def test_known_noncreating_rejection_is_not_unknown(self):
        _, token = self.grant()
        payload = {"head": "run-a-branch", "base": "main", "marker": "request-1"}

        def reject(*_):
            self.calls.append("rejected")
            raise KnownRejected("validation_failed")

        first = self.invoke(token, "pr_create", payload, "effect-1", transport=reject)
        repeated = self.invoke(token, "pr_create", payload, "effect-1", transport=reject)
        self.assertEqual(first, {"state": "rejected", "error": "validation_failed"})
        self.assertEqual(repeated, {**first, "resent": False})
        self.assertEqual(len(self.calls), 1)

    def test_new_run_cannot_hide_uncertain_pr_behind_new_effect_id(self):
        _, a = self.grant()
        _, b = self.grant(run="run-b", branch="run-a-branch")
        first = {"head": "run-a-branch", "base": "main", "marker": "first"}
        second = {**first, "marker": "different-marker"}

        def lost(repository, operation, body):
            self.calls.append((repository, operation, body))
            raise ConnectionError("upstream accepted; reply missing")

        self.assertEqual(self.invoke(a, "pr_create", first, "effect-1", transport=lost)["state"],
                         "unknown")
        self.assert_code("prior_effect_unknown", lambda: self.invoke(
            b, "pr_create", second, "effect-2"))
        self.assertEqual(len(self.calls), 1)
        self.store.authorize_new_attempt(prior_run_id="run-a", prior_effect_id="effect-1",
                                         next_run_id="run-b", next_effect_id="effect-2",
                                         approved_by="user-reviewed-duplicate-risk")
        self.assertEqual(self.invoke(b, "pr_create", second, "effect-2")["state"],
                         "confirmed")
        self.assertEqual(len(self.calls), 2)
        # No third attempt is silently authorized by the one-use approval.
        self.assert_code("prior_effect_unknown", lambda: self.invoke(
            b, "pr_create", {**first, "marker": "third"}, "effect-3"))

    def test_confirmed_target_blocks_new_pr_create(self):
        _, a = self.grant()
        _, b = self.grant(run="run-b", branch="run-a-branch")
        first = {"head": "run-a-branch", "base": "main", "marker": "first"}
        self.invoke(a, "pr_create", first, "effect-1")
        self.assert_code("target_already_confirmed", lambda: self.invoke(
            b, "pr_create", {**first, "marker": "new"}, "effect-2"))
        self.assertEqual(len(self.calls), 1)

    def test_repository_branch_operation_review_and_api_boundaries(self):
        _, token = self.grant()
        self.assert_code("repository_denied", lambda: self.invoke(
            token, "pr_list", repository="wrong/repo"))
        self.assert_code("operation_denied", lambda: self.invoke(token, "issue_list"))
        self.assert_code("push_branch_denied", lambda: self.invoke(
            token, "git_push", {"branch": "other", "commit": "a" * 40}, "effect-1"))
        self.assert_code("pr_head_denied", lambda: self.invoke(
            token, "pr_create", {"head": "other", "base": "main", "marker": "x"}, "effect-2"))
        self.assert_code("unsupported_operation", lambda: self.invoke(token, "auth_token"))
        _, api = self.grant(run="api", operations={"api_rest_write", "api_graphql_mutation"}, branch=None)
        self.assert_code("api_write_unsupported", lambda: self.invoke(
            api, "api_rest_write", {"semantic_operation": "pr_create"}, "api-1"))
        self.assert_code("api_write_unsupported", lambda: self.invoke(
            api, "api_graphql_mutation", {"semantic_operation": "issue_create"}, "api-2"))
        self.assertEqual(self.calls, [])

        approved = {"reviewed_proposal_id": "proposal-1", "marker": "x",
                    "title": "Reviewed follow-up", "body": "Exact reviewed body"}
        _, issue_token = self.grant(run="reviewed", operations={"issue_create"},
                                    branch=None, issues={"proposal-1": approved})
        self.assert_code("issue_review_denied", lambda: self.invoke(
            issue_token, "issue_create", {"reviewed_proposal_id": "proposal-2",
                                          "marker": "x"}, "issue-1"))
        self.assert_code("issue_review_denied", lambda: self.invoke(
            issue_token, "issue_create", {**approved, "body": "Unreviewed edit"}, "issue-1"))
        result = self.invoke(issue_token, "issue_create", approved, "issue-1")
        self.assertEqual(result["state"], "confirmed")

    def test_pr_update_requires_bound_number_head_and_base(self):
        _, token = self.grant(operations={"pr_update"}, target_prs={7: "main"})
        payload = {"number": 7, "head": "run-a-branch", "base": "main",
                   "marker": "reviewed"}
        for changed in ({**payload, "number": 999},
                        {**payload, "head": "other-branch"},
                        {**payload, "base": "other-base"}):
            self.assert_code("target_pr_denied", lambda changed=changed: self.invoke(
                token, "pr_update", changed, "effect-1"))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.invoke(token, "pr_update", payload, "effect-1")["state"],
                         "confirmed")

    def test_pr_read_is_limited_to_bound_target_and_current_head(self):
        _, token = self.grant(operations={"pr_read"}, target_prs={7: "main"})
        self.assert_code("pr_read_target_denied", lambda: self.invoke(
            token, "pr_read", {"number": 8}))
        self.assert_code("pr_read_target_invalid", lambda: self.invoke(
            token, "pr_read", {"number": 7, "path": "/repos/other/repo"}))
        self.assertEqual(self.calls, [])

        def fetched(*_):
            return {"number": 7, "title": "Title", "body": "Body", "base": "main",
                    "head": {"repository": REPO, "branch": "run-a-branch",
                             "sha": "a" * 40}}

        result = self.invoke(token, "pr_read", {"number": 7}, transport=fetched)
        self.assertEqual(result["state"], "confirmed")
        self.assertEqual(result["result"]["body"], "Body")
        changed = dict(fetched())
        changed["head"] = {**changed["head"], "branch": "unapproved"}
        self.assertEqual(self.invoke(
            token, "pr_read", {"number": 7}, transport=lambda *_: changed),
            {"state": "rejected", "error": "pr_target_changed"})
        for malformed in ("unexpected", ["unexpected"], 42):
            self.assertEqual(self.invoke(token, "pr_read", {"number": 7},
                transport=lambda *_: {**fetched(), "head": malformed}),
                {"state": "rejected", "error": "pr_target_changed"})

    def test_revocation_after_local_freeze_preserves_uncertainty(self):
        _, token = self.grant(operations={"git_push"})
        captures = []
        def capture(grant, payload):
            captures.append(payload["attempt_id"])
            self.store.revoke_run(grant["run_id"])
            return {"status": "frozen"}
        self.store.stage_freezer = capture
        self.assertEqual(self.invoke(token, "bundle_freeze", {"attempt_id": "once"}),
                         {"state": "unknown", "resent": False})
        self.assertEqual(captures, ["once"])

        self.assertEqual(self.calls, [])
        self.assert_code("grant_unavailable", lambda: self.invoke(
            token, "bundle_freeze", {"attempt_id": "once"}))
        self.assertEqual(captures, ["once"])

    def test_bundle_status_is_lookup_only_and_rechecks_exact_grant(self):
        _, token = self.grant(operations={"git_push"})
        payload = {"stage_attempt_id": "attempt-a", "commit": "a" * 40}
        lookups = []
        def resolve(grant, repository, request):
            lookups.append(request)
            return SimpleNamespace(run_id=grant["run_id"], repository=repository,
                branch=grant["branch"], commit=request["commit"],
                attempt_id=request["stage_attempt_id"], stage_digest="digest")
        self.store.verified_stage_resolver = resolve
        self.assertEqual(self.invoke(token, "bundle_status", payload)["state"], "confirmed")
        self.assertEqual(self.invoke(token, "bundle_status", payload)["state"], "confirmed")
        self.assertEqual(self.calls, [])
        self.assertEqual(len(lookups), 2)
        def revoke(grant, repository, request):
            value = resolve(grant, repository, request)
            self.store.revoke_run(grant["run_id"])
            return value
        self.store.verified_stage_resolver = revoke
        self.assertEqual(self.invoke(token, "bundle_status", payload),
                         {"state": "unknown", "resent": False})
        self.assert_code("grant_unavailable", lambda: self.invoke(token, "bundle_status", payload))
        self.assertEqual(self.calls, [])

    def test_read_labels_cannot_hide_mutations(self):
        _, token = self.grant(operations={"api_rest_read"}, branch=None)
        for payload in ({"path": "/repos/example/disposable/issues/1", "method": "POST"},
                        {"path": "/repos/other/repo/issues/1"},
                        {"path": "/repos/example/disposable/../other"}):
            self.assert_code("api_read_denied", lambda payload=payload: self.invoke(
                token, "api_rest_read", payload))
        self.assert_code("unsupported_operation", lambda: self.invoke(
            token, "api_graphql_read", {"query": "mutation { deleteRef(...) }"}))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.invoke(token, "api_rest_read", {
            "path": "/repos/example/disposable/issues/1"})["state"], "confirmed")

    def test_workflow_diff_is_trusted_not_agent_flag(self):
        _, token = self.grant(operations={"git_push"})
        commit = "a" * 40
        self.workflow_changes.add(commit)
        self.assert_code("workflow_approval_required", lambda: self.invoke(
            token, "git_push", {"branch": "run-a-branch", "commit": commit,
                                "workflow_file_change": False}, "effect-1"))
        self.assertEqual(self.calls, [])
        reopened = MediationStore(self.path, now=lambda: self.clock[0])
        self.assert_code("push_diff_unverified", lambda: reopened.invoke(
            token=token, repository=REPO, operation="git_push",
            payload={"branch": "run-a-branch", "commit": "b" * 40},
            effect_id="effect-2", transport=self.transport))

    def test_expiry_denies_use_without_any_revocation(self):
        _, token = self.grant(operations={"pr_list"})
        self.clock[0] += 61
        self.assert_code("grant_unavailable", lambda: self.invoke(token, "pr_list"))
        self.assertEqual(self.calls, [])

    def test_wall_clock_rollback_cannot_extend_grant(self):
        wall, mono = [1000.0], [500.0]
        store = MediationStore(self.path, now=lambda: wall[0],
                               monotonic=lambda: mono[0])
        grant_id, token = store.issue(
            run_id="clock-run", invocation_id="clock-invocation",
            repository=REPO, operations={"pr_list"}, ttl_seconds=50)
        wall[0] = 900.0  # A backward wall-clock step cannot extend access.
        mono[0] = 551.0
        self.assert_code("grant_unavailable", lambda: store.invoke(
            token=token, repository=REPO, operation="pr_list", payload={},
            effect_id=None, transport=self.transport))
        self.assertFalse(store.renew_grant(grant_id, 50))
        self.assertEqual(self.calls, [])

    def test_old_grant_without_monotonic_deadline_fails_closed(self):
        _, token = self.grant(operations={"pr_list"})
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE grants SET issued_monotonic=NULL, "
                       "expires_monotonic=NULL")
        self.assert_code("grant_unavailable", lambda: self.invoke(token, "pr_list"))
        self.assertEqual(self.calls, [])

    def test_revoke_and_expire_are_per_run(self):
        grant_a, a = self.grant()
        grant_b, b = self.grant(run="run-b", branch="run-b-branch")
        self.clock[0] += 30
        self.assertTrue(self.store.renew_grant(grant_b, 60))
        self.assertEqual(self.store.revoke_run("run-a"), 1)
        self.assertFalse(self.store.renew_grant(grant_a, 60))
        self.assert_code("grant_unavailable", lambda: self.invoke(a, "pr_list"))
        self.assertEqual(self.invoke(b, "pr_list")["state"], "confirmed")
        self.clock[0] += 61
        self.assertFalse(self.store.renew_grant(grant_b, 60))
        self.assert_code("grant_unavailable", lambda: self.invoke(b, "pr_list"))

    def test_concurrent_same_effect_dispatches_once(self):
        _, token = self.grant()
        entered, release = threading.Event(), threading.Event()
        results = []
        payload = {"head": "run-a-branch", "base": "main", "marker": "request-1"}

        def slow(repository, operation, body):
            self.calls.append((repository, operation, body))
            entered.set()
            self.assertTrue(release.wait(5))
            return {"number": 1}

        worker = threading.Thread(target=lambda: results.append(
            self.invoke(token, "pr_create", payload, "effect-1", transport=slow)))
        worker.start()
        self.assertTrue(entered.wait(5))
        duplicate = self.invoke(token, "pr_create", payload, "effect-1")
        self.assertEqual(duplicate, {"state": "unknown", "resent": False})
        release.set()
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results[0]["state"], "confirmed")
        self.assertEqual(len(self.calls), 1)

    def test_caller_cannot_change_nested_payload_after_journal_hash(self):
        _, token = self.grant()
        payload = {"head": "run-a-branch", "base": "main", "marker": "request-1",
                   "body": {"text": "reviewed"}}

        def mutate_caller(repository, operation, forwarded):
            payload["body"]["text"] = "changed after dispatch"
            self.calls.append(forwarded)
            return {"accepted": True}

        result = self.invoke(token, "pr_create", payload, "effect-1",
                             transport=mutate_caller)
        self.assertEqual(result["state"], "confirmed")
        self.assertEqual(self.calls[0]["body"]["text"], "reviewed")
        self.assert_code("effect_conflict", lambda: self.invoke(
            token, "pr_create", payload, "effect-1"))


if __name__ == "__main__":
    unittest.main()
