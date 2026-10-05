"""Dispatch decisions from complete Work Graph evidence, never a filtered view."""

from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from laomedo.work_graph.github import import_pages
from laomedo.work_graph.launch import launch_github_work_stage, launch_work_stage, preflight
from laomedo.workflow_run_store import LaunchError, WorkflowRunStore


CORPUS = Path(__file__).resolve().parents[1] / "experiments" / "exp16" / "corpus.json"
REPO = "verify/exp16"
WORK = "github:S-20"
TIME = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)


def snapshot(corpus, name, fetched_at="2026-10-05T10:00:00+00:00"):
    return import_pages(REPO, corpus[name], fetched_at=fetched_at)


class FakeStage:
    def __init__(self):
        self.calls = 0

    def execute(self, store, *, resolved_config, trigger, **_kwargs):
        self.calls += 1
        run = store.reserve(graph={"nodes": [{"id": "fake"}]},
                            component_code={"fake": "synthetic code"},
                            resolved_config=resolved_config, trigger=trigger)
        return store.get(run["run_id"]), store.dispatch(run["run_id"], lambda _: "DONE")


class WorkGraphLaunchTests(unittest.TestCase):
    def setUp(self):
        self.corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        self.frozen = snapshot(self.corpus, "base")
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = WorkflowRunStore(Path(temporary.name) / "runs.sqlite3")
        self.stage = FakeStage()

    def grant(self, ref, binding):
        return {"grant_id": ref, "operator_authorized": True,
            "work_key": WORK, "graph_snapshot_id": binding["selected_graph_snapshot_id"],
            "runner": "langflow-local", "scope": "stage-launch",
            "expires_at": "2026-10-05T10:10:00+00:00",
            "limits": {"timeout_seconds": 60, "max_turns": 0}}

    def launch(self, current, **kwargs):
        return launch_work_stage(frozen=self.frozen,
            source_fetch=lambda repository: current if repository == REPO else None,
            work_key=WORK,
            stage=self.stage, store=self.store, grant_ref="synthetic-grant",
            grant_authority=self.grant, resolved_config={"provider": "fake"},
            now=TIME, **kwargs)

    def test_refetch_only_changes_snapshot_id_not_content_choice(self):
        refetched = snapshot(self.corpus, "base", "2026-10-05T10:01:00+00:00")
        decision = preflight(self.frozen, refetched, WORK)
        self.assertNotEqual(decision["selected_graph_snapshot_id"],
                            decision["authorization_graph_snapshot_id"])
        self.assertEqual(decision["frozen_content_digest"],
                         decision["authorization_content_digest"])
        record, result = self.launch(refetched)
        self.assertEqual(result, "DONE")
        self.assertEqual(json.loads(record["trigger_json"])["source_choice"], "unchanged")
        self.assertEqual(self.store.counters()["dispatch_attempts"], 1)

    def test_changed_source_requires_choice_and_pinned_records_both_graphs(self):
        changed = snapshot(self.corpus, "content_changed")
        with self.assertRaisesRegex(LaunchError, "stale_unacknowledged"):
            self.launch(changed)
        self.assertEqual(self.store.counters()["runs"], 0)
        pinned = preflight(self.frozen, changed, WORK, choice="pinned")
        refreshed = preflight(self.frozen, changed, WORK, choice="refreshed")
        self.assertEqual(pinned["selected_graph_snapshot_id"], self.frozen.snapshot_id)
        self.assertEqual(pinned["authorization_graph_snapshot_id"], changed.snapshot_id)
        self.assertEqual(refreshed["selected_graph_snapshot_id"], changed.snapshot_id)
        self.assertNotEqual(pinned["input_digest"], refreshed["input_digest"])

    def test_new_hidden_blocker_and_unknown_or_cyclic_evidence_refuse(self):
        opened = snapshot(self.corpus, "opened_blocker")
        self.assertEqual(opened.project("open", ("work",))["items"][0]["readiness"], "blocked")
        for name, choice, reason in (
            ("opened_blocker", "pinned", "open_prerequisite"),
            ("unresolved_external", "refreshed", "prerequisite_unknown"),
            ("cycle", "pinned", "prerequisite_cyclic"),
            ("incomplete", "refreshed", "source_incomplete"),
        ):
            with self.subTest(name=name), self.assertRaisesRegex(LaunchError, reason):
                self.launch(snapshot(self.corpus, name), choice=choice)
        self.assertEqual(self.store.counters()["runs"], 0)

    def test_only_exact_known_open_edge_with_rationale_can_override(self):
        opened = snapshot(self.corpus, "opened_blocker")
        valid = {"prerequisite": "github:C-10", "dependent": WORK,
                 "rationale": "Reviewed synthetic exception"}
        for bad in ({**valid, "prerequisite": "github:I-30"},
                    {**valid, "rationale": ""},
                    {**valid, "dependent": "github:I-30"}):
            with self.assertRaisesRegex(LaunchError, "open_prerequisite"):
                self.launch(opened, choice="pinned", override=bad)
        record, _ = self.launch(opened, choice="pinned", override=valid)
        saved = json.loads(record["trigger_json"])
        self.assertEqual(saved["override"], valid)
        self.assertEqual(saved["authorization_graph_snapshot_id"], opened.snapshot_id)
        self.assertEqual(saved["selected_graph_snapshot_id"], self.frozen.snapshot_id)

    def test_missing_or_invalid_grant_refuses_before_reservation(self):
        valid = self.grant("synthetic-grant", preflight(self.frozen, self.frozen, WORK))
        for change, reason in (({"operator_authorized": False}, "operator_not_authorized"),
                               ({"work_key": "other"}, "grant_wrong_work"),
                               ({"graph_snapshot_id": "wrong"}, "grant_wrong_graph"),
                               ({"runner": "other"}, "grant_wrong_runner"),
                               ({"scope": "read"}, "grant_wrong_scope"),
                               ({"limits": {}}, "grant_limits_invalid"),
                               ({"expires_at": "2026-10-05T09:00:00+00:00"}, "grant_expired")):
            with self.subTest(change=change):
                altered = {**valid, **change}
                with self.assertRaisesRegex(LaunchError, reason):
                    launch_work_stage(frozen=self.frozen,
                        source_fetch=lambda _repository: self.frozen,
                        work_key=WORK, stage=self.stage, store=self.store,
                        grant_ref="synthetic-grant",
                        grant_authority=lambda _ref, _binding: altered,
                        resolved_config={"provider": "fake"}, now=TIME)
        with self.assertRaisesRegex(LaunchError, "grant_authority_required"):
            launch_work_stage(frozen=self.frozen,
                source_fetch=lambda _repository: self.frozen,
                work_key=WORK, stage=self.stage, store=self.store,
                grant_ref="synthetic-grant", grant_authority=None,
                resolved_config={"provider": "fake"}, now=TIME)
        with self.assertRaisesRegex(LaunchError, "source_refresh_required"):
            launch_work_stage(frozen=self.frozen, source_fetch=None,
                work_key=WORK, stage=self.stage, store=self.store,
                grant_ref="synthetic-grant", grant_authority=self.grant,
                resolved_config={"provider": "fake"}, now=TIME)
        self.assertEqual(self.store.counters()["runs"], 0)
        self.assertEqual(self.stage.calls, 0)

    def test_github_entrypoint_refreshes_before_any_reservation(self):
        changed = snapshot(self.corpus, "content_changed")
        with patch("laomedo.work_graph.github.fetch", return_value=changed) as fetch:
            with self.assertRaisesRegex(LaunchError, "stale_unacknowledged"):
                launch_github_work_stage(frozen=self.frozen, work_key=WORK,
                    stage=self.stage, store=self.store, grant_ref="synthetic-grant",
                    grant_authority=self.grant, resolved_config={"provider": "fake"},
                    now=TIME)
            fetch.assert_called_once_with(REPO)
        self.assertEqual(self.store.counters()["runs"], 0)
        self.assertEqual(self.stage.calls, 0)


if __name__ == "__main__":
    unittest.main()
