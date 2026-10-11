"""Durable live-experiment limits, without provider access or credentials."""
from pathlib import Path
from contextlib import closing
import sqlite3
import sys
import tempfile
import unittest
sys.path.append(str(Path(__file__).resolve().parents[1]))
from experiments.exp139.prepare import BRANCH, REPOSITORY
from experiments.exp139.runtime import WriteBudget
from laomedo.github_mediation import MediationStore, KnownRejected
from laomedo.output_contract import requirements


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = MediationStore(self.root / "effects.sqlite")
        self.calls = []
        self.budget = WriteBudget(self.root / "budget.sqlite", self.send, self.store)

    def send(self, repository, operation, payload, **binding):
        self.calls.append(operation)
        if getattr(self, "lose_response", False):
            raise TimeoutError("fixture unknown")
        return {"fixture": True}

    def test_push_is_single_attempt_even_after_unknown_and_restart(self):
        self.lose_response = True
        with self.assertRaises(TimeoutError):
            self.budget(REPOSITORY, "git_push", {"branch": BRANCH})
        fresh = WriteBudget(self.root / "budget.sqlite", self.send, self.store)
        with self.assertRaisesRegex(KnownRejected, "experiment_write_budget_consumed"):
            fresh(REPOSITORY, "git_push", {"branch": BRANCH})
        self.assertEqual(self.calls, ["git_push"])

    def test_other_repository_branch_operation_refuse_without_consuming_budget(self):
        for repo, op, payload in (("other/repo", "git_push", {"branch": BRANCH}),
                                  (REPOSITORY, "git_push", {"branch": "other"}),
                                  (REPOSITORY, "issue_create", {})):
            with self.assertRaises(KnownRejected):
                self.budget(repo, op, payload)
        self.assertEqual(self.calls, [])
        self.budget(REPOSITORY, "git_push", {"branch": BRANCH})
        self.assertEqual(self.calls, ["git_push"])

    def test_agent_lane_cannot_spend_pr_budget(self):
        # No pending host handoff exists. A graph/agent cannot manufacture it.
        payload = {"head": BRANCH, "draft": True}
        with self.assertRaisesRegex(KnownRejected, "experiment_publisher_lane_required"):
            self.budget(REPOSITORY, "pr_create", payload)
        self.assertEqual(self.calls, [])
        with closing(sqlite3.connect(self.root / "budget.sqlite")) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0], 0)

    def test_only_pending_publisher_lane_can_attempt_one_pr(self):
        grant, token = self.store.issue(run_id="fixture-run", invocation_id="fixture-invocation",
            repository=REPOSITORY, branch=BRANCH, operations={"git_push", "pr_create"},
            ttl_seconds=30)
        form = requirements({"schema_version": 1, "fields": []})
        self.store.begin_publication_handoff(token=token, repository=REPOSITORY,
            requirements=form, deadline=self.store.now() + 20,
            deadline_monotonic=self.store.monotonic() + 20)
        payload = {"head": BRANCH, "draft": True}
        with self.assertRaises(KnownRejected):
            self.budget(REPOSITORY, "pr_create", payload)
        with closing(self.store._connect()) as db, db:
            db.execute("UPDATE publication_handoffs SET phase='publication_pending' WHERE grant_id=?", (grant,))
        # A previous failed run remains recorded and must not prevent recovery.
        old_grant, old_token = self.store.issue(run_id="old-run", invocation_id="old-invocation",
            repository=REPOSITORY, branch=BRANCH, operations={"git_push", "pr_create"}, ttl_seconds=30)
        self.store.begin_publication_handoff(token=old_token, repository=REPOSITORY,
            requirements=form, deadline=self.store.now()+20, deadline_monotonic=self.store.monotonic()+20)
        with closing(self.store._connect()) as db, db:
            db.execute("UPDATE publication_handoffs SET phase='rejected' WHERE grant_id=?", (old_grant,))
        self.budget(REPOSITORY, "pr_create", payload)
        with self.assertRaisesRegex(KnownRejected, "experiment_write_budget_consumed"):
            self.budget(REPOSITORY, "pr_create", payload)
        self.assertEqual(self.calls, ["pr_create"])
