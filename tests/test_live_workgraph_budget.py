"""Durable live-experiment limits, without provider access or credentials."""
from pathlib import Path
from contextlib import closing
import sqlite3
import tempfile
import unittest
from experiments.exp139.prepare import BRANCH, REPOSITORY
from experiments.exp139.runtime import WriteBudget
from laomedo.github_mediation import MediationStore, KnownRejected


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
