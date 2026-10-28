"""Durable live-experiment limits, without provider access or credentials."""
from pathlib import Path
from contextlib import closing
import sqlite3
import json
from unittest.mock import patch
import sys
import tempfile
import unittest
sys.path.append(str(Path(__file__).resolve().parents[1]))
from experiments.exp139.prepare import BRANCH; from experiments.exp139.prepare import REPOSITORY; from experiments.exp139.prepare import report_task
from experiments.exp139.runtime import WriteBudget; from experiments.exp139.runtime import configuration
from laomedo.host.mediation.store import MediationStore; from laomedo.host.mediation.errors import KnownRejected
from laomedo.agents.contracts.output import requirements


class BudgetTests(unittest.TestCase):
    def test_report_task_encodes_exact_bytes_and_requires_command_completion(self):
        import base64
        from hashlib import sha256
        report = "# Fixture\nOne final newline\n"
        task = report_task(report, "fixture-branch")
        marker = "by decoding this base64 into bytes (do not use a heredoc or add a newline): "
        encoded = task.split(marker, 1)[1].split(". ", 1)[0]
        self.assertEqual(base64.b64decode(encoded), report.encode())
        self.assertIn(sha256(report.encode()).hexdigest(), task)
        self.assertIn("Wait for the push shell command to finish", task)
        self.assertIn("Do not retry an uncertain push", task)

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

    def test_interactive_campaign_refuses_budget_widening_and_old_ledger(self):
        config = {"identity": "langflow-demo-20261012-c", "repository": REPOSITORY,
                  "branch": "langflow-demo-20261012-c", "turn_cap": 4,
                  "runner_port": 8779, "handoff_seconds": 600}
        with patch("experiments.exp139.runtime._outside_git", return_value=self.root):
            for changes in ({}, {"turn_cap": 5}, {"branch": BRANCH},
                            {"prior_turns": 8}, {"previous_consumed": []},
                            {"handoff_seconds": 601}):
                (self.root / "config.json").write_text(json.dumps(config | changes))
                if changes:
                    with self.assertRaisesRegex(ValueError, "frozen_configuration_required"):
                        configuration(self.root)
                else:
                    self.assertEqual(configuration(self.root)[1], config)

    def test_interactive_push_bound_to_new_branch_with_independent_budget(self):
        branch = "langflow-demo-20261012-c"
        fresh = WriteBudget(self.root / "interactive.sqlite", self.send, self.store, branch=branch)
        with self.assertRaisesRegex(KnownRejected, "experiment_branch_denied"):
            fresh(REPOSITORY, "git_push", {"branch": BRANCH})
        fresh(REPOSITORY, "git_push", {"branch": branch})
        restarted = WriteBudget(self.root / "interactive.sqlite", self.send, self.store, branch=branch)
        with self.assertRaisesRegex(KnownRejected, "experiment_write_budget_consumed"):
            restarted(REPOSITORY, "git_push", {"branch": branch})
        with closing(sqlite3.connect(self.root / "budget.sqlite")) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0], 0)
        self.assertEqual(self.calls, ["git_push"])

    def test_push_is_single_attempt_even_after_unknown_and_restart(self):
        self.lose_response = True
        with self.assertRaises(TimeoutError):
            self.budget(REPOSITORY, "git_push", {"branch": BRANCH})
        fresh = WriteBudget(self.root / "budget.sqlite", self.send, self.store)
        with self.assertRaisesRegex(KnownRejected, "experiment_write_budget_consumed"):
            fresh(REPOSITORY, "git_push", {"branch": BRANCH})
        self.assertEqual(self.calls, ["git_push"])

    def test_fresh_campaign_requires_exact_prior_budget_without_resetting_it(self):
        prior = self.root / "prior.sqlite"
        with closing(sqlite3.connect(prior)) as db, db:
            db.execute("CREATE TABLE attempts (operation TEXT PRIMARY KEY)")
            db.execute("INSERT INTO attempts VALUES ('git_push')")
        budget = WriteBudget(self.root / "fresh.sqlite", self.send, self.store, prior_write_budget=prior)
        budget(REPOSITORY, "git_push", {"branch": BRANCH})
        with self.assertRaisesRegex(KnownRejected, "experiment_write_budget_consumed"):
            budget(REPOSITORY, "git_push", {"branch": BRANCH})
        with closing(sqlite3.connect(prior)) as db, db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0], 1)
            db.execute("INSERT INTO attempts VALUES ('pr_create')")
        with self.assertRaisesRegex(KnownRejected, "experiment_prior_budget_changed"):
            budget(REPOSITORY, "pr_create", {"head": BRANCH, "draft": True})
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
