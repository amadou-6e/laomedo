"""Durability and dispatch refusal at the synthetic workflow boundary."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from laomedo.workflow_run_store import ExternalOutcomeUnknown, LaunchError, WorkflowRunStore


FLOW = Path(__file__).resolve().parents[1] / "experiments" / "exp03" / "flow.json"


class WorkflowRunStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = WorkflowRunStore(Path(self.temp.name) / "runs.sqlite3")
        self.graph = json.loads(FLOW.read_text(encoding="utf-8"))["data"]
        marker = next(n for n in self.graph["nodes"] if n["id"] == "Exp03Marker-exp03")
        self.code = {marker["id"]: marker["data"]["node"]["template"]["code"]["value"]}

    def reserve(self, **override):
        args = {"graph": self.graph, "component_code": self.code,
                "resolved_config": {"mode": "synthetic"}, "trigger": {"type": "direct"}}
        args.update(override)
        return self.store.reserve(**args)

    def test_dispatch_requires_durable_identity_and_exactly_one_attempt(self):
        called = []
        with self.assertRaisesRegex(LaunchError, "unresolved_launch_identity"):
            self.reserve(resolved_config={})
        with self.assertRaisesRegex(LaunchError, "unresolved_component_identity"):
            self.reserve(component_code={"missing": "code"})
        with self.assertRaisesRegex(LaunchError, "dispatch_not_reserved"):
            self.store.dispatch("missing", lambda _: called.append(True))
        self.assertEqual(called, [])
        record = self.reserve()
        self.assertEqual(record["status"], "reserved")
        self.assertTrue(record["trace_id"] and record["graph_revision"] and
                        record["resolved_config_ref"] and record["component_revisions"])
        self.assertEqual(self.store.dispatch(record["run_id"], self.store.record_synthetic_dispatch), 1)
        with self.assertRaisesRegex(LaunchError, "dispatch_not_reserved"):
            self.store.dispatch(record["run_id"], lambda _: called.append(True))
        self.assertEqual(called, [])
        self.assertEqual(self.store.counters()["synthetic_dispatches"], 1)

    def test_restart_sweeps_only_nonterminal_without_redispatch(self):
        reserved = self.reserve()
        completed = self.reserve()
        self.store.dispatch(completed["run_id"], self.store.record_synthetic_dispatch)
        self.assertEqual(self.store.sweep_crashed(), [reserved["run_id"]])
        self.assertEqual(self.store.get(reserved["run_id"])["status"], "crashed")
        self.assertEqual(self.store.get(completed["run_id"])["status"], "completed")
        self.assertEqual(self.store.sweep_crashed(), [])
        self.assertEqual(self.store.counters()["synthetic_dispatches"], 1)

    def test_process_exit_completion_does_not_claim_complete_evidence(self):
        record = self.reserve()
        with self.assertRaisesRegex(LaunchError, "completion_basis_invalid"):
            self.store.dispatch(record["run_id"], lambda _: "unused",
                                completion_basis="unverified")
        self.assertEqual(self.store.get(record["run_id"])["status"], "reserved")
        self.assertEqual(self.store.dispatch(record["run_id"],
            lambda _: "untrusted output", completion_basis="process_exit"),
            "untrusted output")
        saved = self.store.get(record["run_id"])
        self.assertEqual(saved["status"], "completed")
        self.assertEqual(saved["completion_basis"], "process_exit")
        self.assertEqual(saved["evidence_complete"], 0)
        self.assertEqual(saved["dispatch_attempts"], 1)
        self.assertEqual(WorkflowRunStore(self.store.path).get(record["run_id"]), saved)

    def test_lost_external_acknowledgement_stays_unknown_and_never_retries(self):
        record = self.reserve(trigger={"type": "selected-issue"})
        submitted = []

        def lose_acknowledgement(run_id):
            submitted.append(run_id)
            raise ExternalOutcomeUnknown("transport_lost_after_send")

        with self.assertRaises(ExternalOutcomeUnknown):
            self.store.dispatch(record["run_id"], lose_acknowledgement)
        saved = self.store.get(record["run_id"])
        self.assertEqual(saved["status"], "unknown")
        self.assertEqual(saved["terminal_reason"], "external_outcome_unknown")
        self.assertEqual(saved["dispatch_attempts"], 1)
        self.assertEqual(saved["evidence_complete"], 0)
        self.assertEqual(self.store.sweep_crashed(), [])
        with self.assertRaisesRegex(LaunchError, "dispatch_not_reserved"):
            self.store.dispatch(record["run_id"], lose_acknowledgement)
        self.assertEqual(submitted, [record["run_id"]])


if __name__ == "__main__":
    unittest.main()
