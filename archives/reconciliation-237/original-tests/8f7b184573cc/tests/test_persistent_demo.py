"""Credential-free checks of standing per-run allowance, never live writes."""

from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import sqlite3
import tempfile
import threading
import unittest
from uuid import uuid4

from retained_github import load_retained_github

load_retained_github("experiments.exp139.runtime")
from experiments.exp139.persistent_demo import PerRunWriteBudget
from experiments.exp139.persistent_demo import PersistentRunner
from experiments.exp139.persistent_demo import policy
from experiments.exp139.prepare import REPOSITORY
from experiments.exp139.prepare import save
from laomedo.host.mediation.errors import KnownRejected
from laomedo.host.mediation.store import MediationStore
from laomedo.agents.errors import RunnerError


class StandingBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = MediationStore(self.root / "store.db")
        self.calls = []
        self.budget = PerRunWriteBudget(self.root / "budget.db", self.send, self.store)

    def send(self, *args, **kwargs):
        self.calls.append(args)
        if getattr(self, "lose_response", False):
            raise TimeoutError("unknown provider outcome")
        return {"fixture": True}

    def push(self, run_id):
        branch = "laomedo-dev-" + run_id.replace("-", "")
        stage = SimpleNamespace(run_id=run_id, branch=branch, repository=REPOSITORY)
        return self.budget(
            REPOSITORY, "git_push", {"branch": branch}, verified_stage=stage
        )

    def test_independent_run_budgets_survive_restart_and_unknown(self):
        first, second = str(uuid4()), str(uuid4())
        self.lose_response = True
        with self.assertRaises(TimeoutError):
            self.push(first)
        self.budget = PerRunWriteBudget(self.root / "budget.db", self.send, self.store)
        with self.assertRaisesRegex(
            KnownRejected, "standing_run_write_budget_consumed"
        ):
            self.push(first)
        self.lose_response = False
        self.push(second)
        self.assertEqual(len(self.calls), 2)
        with closing(sqlite3.connect(self.root / "budget.db")) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM per_run_attempts").fetchone()[0], 2
            )

    def test_scope_and_unverified_push_refuse_without_spending(self):
        for repository, branch in (
            ("other/repo", "laomedo-dev-" + "a" * 32),
            (REPOSITORY, "main"),
        ):
            with self.assertRaises(KnownRejected):
                self.budget(repository, "git_push", {"branch": branch})
        with self.assertRaisesRegex(KnownRejected, "standing_verified_stage_required"):
            self.budget(REPOSITORY, "git_push", {"branch": "laomedo-dev-" + "a" * 32})
        self.assertEqual(self.calls, [])

    def test_policy_cannot_silently_widen_limits(self):
        expected = {
            "repository": REPOSITORY,
            "turns_per_run": 4,
            "pushes_per_run": 1,
            "draft_prs_per_run": 1,
            "enabled": True,
        }
        for changed in (
            {},
            {"turns_per_run": 5},
            {"pushes_per_run": 2},
            {"enabled": "true"},
            {"repository": "other/repo"},
            {"pushes_per_run": True},
        ):
            save(self.root / "standing-policy.json", expected | changed)
            if changed:
                with self.assertRaises(RunnerError):
                    policy(self.root)
            else:
                self.assertEqual(policy(self.root), expected)

    def test_each_run_has_four_turns_and_restart_keeps_counts(self):
        node = PersistentRunner.__new__(PersistentRunner)
        node.state = self.root
        node.local_run = threading.local()
        for run_id in (str(uuid4()), str(uuid4())):
            (self.root / "runs" / run_id).mkdir(parents=True)
            node.local_run.run_id = run_id
            for expected in range(1, 5):
                self.assertEqual(node._reserve_turn(), expected)
            with self.assertRaisesRegex(RunnerError, "model_turn_cap_reached"):
                node._reserve_turn()
            node.local_run = threading.local()
            node.local_run.run_id = run_id
            with self.assertRaises(RunnerError):
                node._reserve_turn()
        node.local_run.run_id = None
        with self.assertRaisesRegex(RunnerError, "per_run_ledger_required"):
            node._reserve_turn()

    def test_policy_disabled_refuses_before_grant(self):
        save(
            self.root / "standing-policy.json",
            {
                "repository": REPOSITORY,
                "turns_per_run": 4,
                "pushes_per_run": 1,
                "draft_prs_per_run": 1,
                "enabled": False,
            },
        )
        node = PersistentRunner.__new__(PersistentRunner)
        node.policy_root = self.root
        with patch.object(node, "authorization_factory", create=True) as authorize:
            with self.assertRaisesRegex(RunnerError, "standing_policy_inactive"):
                node._prepare({})
            authorize.assert_not_called()

    def test_draft_budget_requires_pending_handoff_and_is_per_run(self):
        from laomedo.agents.interface.output.utils import requirements

        for run_id in (str(uuid4()), str(uuid4())):
            branch = "laomedo-dev-" + run_id.replace("-", "")
            grant, token = self.store.issue(
                run_id=run_id,
                invocation_id=run_id,
                repository=REPOSITORY,
                branch=branch,
                operations={"git_push", "pr_create"},
                ttl_seconds=30,
            )
            payload = {"head": branch, "draft": True}
            with self.assertRaisesRegex(
                KnownRejected, "standing_publisher_lane_required"
            ):
                self.budget(REPOSITORY, "pr_create", payload)
            self.store.begin_publication_handoff(
                token=token,
                repository=REPOSITORY,
                requirements=requirements({"schema_version": 1, "fields": []}),
                deadline=self.store.now() + 20,
                deadline_monotonic=self.store.monotonic() + 20,
            )
            with closing(self.store._connect()) as db, db:
                db.execute(
                    "UPDATE publication_handoffs SET phase='publication_pending' WHERE grant_id=?",
                    (grant,),
                )
            self.budget(REPOSITORY, "pr_create", payload)
            self.budget = PerRunWriteBudget(
                self.root / "budget.db", self.send, self.store
            )
            with self.assertRaisesRegex(
                KnownRejected, "standing_run_write_budget_consumed"
            ):
                self.budget(REPOSITORY, "pr_create", payload)
        self.assertEqual(len(self.calls), 2)

    def test_new_manual_requests_get_fresh_branches_and_host_tasks(self):
        from laomedo.agents.agents.codex.agent import CodexAgent as LocalRunner
        from laomedo.agents.interface.output.utils import requirements

        save(
            self.root / "standing-policy.json",
            {
                "repository": REPOSITORY,
                "turns_per_run": 4,
                "pushes_per_run": 1,
                "draft_prs_per_run": 1,
                "enabled": True,
            },
        )
        (self.root / "flow-input").mkdir()
        form = {"schema_version": 1, "fields": []}
        save(
            self.root / "flow-input/success.json",
            {
                "data": {
                    "nodes": [
                        {
                            "id": "contract",
                            "data": {
                                "node": {
                                    "template": {
                                        "requirements_json": {"value": json.dumps(form)}
                                    }
                                }
                            },
                        }
                    ]
                }
            },
        )
        skill = {"skill_id": "fixture", "revision_id": "pin", "tree_hash": "pin"}
        save(self.root / "config.json", {"skill": skill})
        node = PersistentRunner.__new__(PersistentRunner)
        node.policy_root, node.state, node.lock = (
            self.root,
            self.root / "runner",
            threading.Lock(),
        )
        node.snapshot, node.report = {"context": "frozen"}, "exact report\n"
        branches, tasks = [], []

        def authorize(branch):
            branches.append(branch)
            return "host-only-reference"

        node.authorization_factory = authorize

        def prepare(_self, selected, **kwargs):
            tasks.append(selected)
            run_id = str(uuid4())
            node._run_dir(run_id).mkdir(parents=True)
            return {"run_id": run_id}

        body = {
            "task": json.dumps(
                {"task": "Readable instructions", "frozen_issue": node.snapshot}
            ),
            "model": "gpt-6-luna",
            "effort": "low",
            "skill_ref": skill,
            "output_requirements": requirements(form),
            "output_retries": 1,
        }
        with patch.object(LocalRunner, "_prepare", new=prepare):
            node._prepare(body)
            node._prepare(body)
            with self.assertRaisesRegex(RunnerError, "standing_pinned_inputs_required"):
                node._prepare(body | {"model": "other"})
        self.assertEqual(len(set(branches)), 2)
        for selected, branch in zip(tasks, branches):
            self.assertIn(branch, json.loads(selected["task"])["task"])
            self.assertIn("Readable instructions", json.loads(selected["task"])["task"])
        self.assertNotIn("github_authorization_ref", body)
