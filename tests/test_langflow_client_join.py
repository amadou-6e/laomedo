"""Credential-free tests for the first-call Langflow client identity fence."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from laomedo.workflow_run_store import LaunchError, WorkflowRunStore


HASH = "sha256:" + "1" * 64
OTHER_HASH = "sha256:" + "2" * 64


class LangflowClientJoinTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "runs.sqlite3"
        self.store = WorkflowRunStore(self.path)

    def reserve(self, *, freeze=True):
        run = self.store.reserve(
            graph={"nodes": [{"id": "agent"}]},
            component_code={"agent": "synthetic source"},
            resolved_config={"task": "synthetic"},
            trigger={"kind": "playground"})
        invocation = self.store.reserve_invocation(run["run_id"], "agent")
        if freeze:
            self.store.freeze_runner_request(run["run_id"], invocation, HASH)
        return run["run_id"], invocation

    def claim(self, client, run, invocation, digest=HASH):
        return self.store.claim_langflow_client(
            client, digest, run_id=run, invocation_id=invocation,
            flow_id="saved-flow", graph_run_id="reported-graph",
            graph_basis="saved_flow_export")

    def test_stop_before_claim_fences_late_start_after_reopen(self):
        client = str(uuid4())
        self.assertIsNone(self.store.request_langflow_cancel(client))
        run, invocation = self.reserve()
        self.assertTrue(self.claim(client, run, invocation)[1])
        reopened = WorkflowRunStore(self.path)
        self.assertEqual(reopened.begin_langflow_client(client),
                         "cancelled_before_dispatch")
        self.assertEqual(reopened.begin_langflow_client(client),
                         "cancelled_before_dispatch")
        trace = reopened.trace_snapshot(run)
        self.assertEqual(trace["dispatch_attempts"], 0)
        self.assertEqual(trace["run_status"], "cancelled")
        self.assertEqual(sum(row["kind"] == "client_cancelled_before_dispatch"
                             for row in trace["receipts"]), 1)

    def test_lost_response_retry_cannot_create_second_attempt(self):
        client = str(uuid4())
        run, invocation = self.reserve()
        first, created = self.claim(client, run, invocation)
        self.assertTrue(created)
        self.assertEqual(self.store.begin_langflow_client(client), "dispatching")
        retry = WorkflowRunStore(self.path)
        second, created = retry.claim_langflow_client(
            client, HASH, run_id=run, invocation_id=invocation,
            graph_basis="saved_flow_export")
        self.assertFalse(created)
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(retry.begin_langflow_client(client), "already_dispatching")
        self.assertEqual(retry.trace_snapshot(run)["dispatch_attempts"], 1)
        self.assertEqual(retry.request_langflow_cancel(client)["run_id"], run)
        self.assertTrue(retry.langflow_cancel_requested(client))

    def test_duplicate_reservation_is_discarded_before_dispatch(self):
        client = str(uuid4())
        winner, winner_invocation = self.reserve()
        loser, loser_invocation = self.reserve()
        self.assertTrue(self.claim(client, winner, winner_invocation)[1])
        binding, created = self.claim(client, loser, loser_invocation)
        self.assertFalse(created)
        self.assertEqual(binding["run_id"], winner)
        discarded = self.store.trace_snapshot(loser)
        self.assertEqual(discarded["run_status"], "cancelled")
        self.assertEqual(discarded["dispatch_attempts"], 0)
        self.assertIn("duplicate_reservation_discarded",
                      [item["kind"] for item in discarded["receipts"]])

    def test_changed_body_and_unfrozen_identity_refuse_before_dispatch(self):
        client = str(uuid4())
        run, invocation = self.reserve(freeze=False)
        with self.assertRaisesRegex(LaunchError, "client_request_not_frozen"):
            self.claim(client, run, invocation)
        self.store.freeze_runner_request(run, invocation, HASH)
        self.claim(client, run, invocation)
        with self.assertRaisesRegex(LaunchError, "client_request_identity_conflict"):
            self.claim(client, run, invocation, OTHER_HASH)
        with self.assertRaisesRegex(LaunchError, "invalid_graph_basis"):
            self.store.claim_langflow_client(
                str(uuid4()), HASH, run_id=run, invocation_id=invocation,
                graph_basis="executing_graph_verified")
        self.assertEqual(self.store.trace_snapshot(run)["dispatch_attempts"], 0)

    def test_stranded_reservation_never_dispatches_after_crash_sweep(self):
        client = str(uuid4())
        run, invocation = self.reserve()
        self.claim(client, run, invocation)
        reopened = WorkflowRunStore(self.path)
        self.assertEqual(reopened.sweep_crashed(), [run])
        with self.assertRaisesRegex(LaunchError, "client_request_not_frozen"):
            reopened.begin_langflow_client(client)
        self.assertEqual(reopened.trace_snapshot(run)["dispatch_attempts"], 0)


if __name__ == "__main__":
    unittest.main()
