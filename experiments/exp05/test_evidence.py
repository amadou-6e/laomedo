"""Bounded EXP-05 synthetic identity and raw/projection tests."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from experiments.exp05.evidence import EvidenceError, EvidenceStore
from experiments.exp05.probe import PHASES, parent
from laomedo.workflow_run_store import WorkflowRunStore


class EvidenceStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="laomedo-exp05-test-")
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name) / "evidence.sqlite3"
        self.runs = WorkflowRunStore(path)
        self.evidence = EvidenceStore(path)
        self.run = self.runs.reserve(
            graph={"nodes": [{"id": "stage"}]},
            component_code={"stage": "synthetic"},
            resolved_config={"model": "none"},
            trigger={"type": "direct"},
        )

    def reserve(self):
        self.evidence.reserve(
            run_id=self.run["run_id"], trace_id=self.run["trace_id"],
            stage_id="stage", invocation_id="invocation-1",
        )

    def test_run_identity_is_checked_and_invocation_is_unique(self):
        with self.assertRaisesRegex(EvidenceError, "run_not_reserved"):
            self.evidence.reserve(
                run_id=self.run["run_id"], trace_id="wrong",
                stage_id="stage", invocation_id="invocation-1",
            )
        self.reserve()
        with self.assertRaisesRegex(EvidenceError, "duplicate_invocation_identity"):
            self.reserve()
        self.assertEqual(self.evidence.inspect()["invocations"][0]["trace_id"],
                         self.run["trace_id"])

    def test_native_id_conflict_does_not_overwrite_identity(self):
        self.reserve()
        self.evidence.record_native_session("invocation-1", "native-1")
        with self.assertRaisesRegex(EvidenceError, "native_session_not_reservable"):
            self.evidence.record_native_session("invocation-1", "native-2")
        self.assertEqual(self.evidence.inspect()["invocations"][0]["native_session_id"],
                         "native-1")

    def test_missing_source_id_remains_absent_and_stream_partial(self):
        self.reserve()
        self.evidence.record_native_session("invocation-1", "native-1")
        self.evidence.append_raw_event(
            "invocation-1", source_event_id=None, kind="message",
            payload={"summary": "possibly replayed"},
        )
        self.evidence.sweep_crashed()
        first = self.evidence.inspect()
        self.assertIsNone(first["raw_events"][0]["source_event_id"])
        self.assertEqual(first["invocations"][0]["stream_state"], "partial")
        self.assertEqual(len(first["projections"]), 1)
        self.assertEqual(self.evidence.sweep_crashed(), [])
        self.assertEqual(self.evidence.project_unprojected(), 0)
        self.assertEqual(len(self.evidence.inspect()["projections"]), 1)
        with self.assertRaisesRegex(EvidenceError, "invocation_not_active"):
            self.evidence.append_raw_event(
                "invocation-1", source_event_id=None, kind="message", payload={},
            )

    def test_probe_checks_every_process_kill_boundary(self):
        self.assertEqual(len(PHASES), 7)
        parent()


if __name__ == "__main__":
    unittest.main()
