"""Controls for source identity, event transitions and falsifiable assessment."""
from copy import deepcopy
import tempfile
import hashlib
import json
from pathlib import Path
import unittest
from experiments.exp123.probe import assess, fixture, validate_capture
from experiments.exp123.runtime import FixtureStore, HEADS


class ProbeTests(unittest.TestCase):
    def test_first_final_cannot_be_overwritten_and_early_event_is_retained(self):
        with tempfile.TemporaryDirectory() as root:
            store = FixtureStore(Path(root) / "journal.jsonl")
            run = "exp123-S1-control"
            store.reserve(run, "control")
            for status in ("unknown", "pending", "failed"):
                self.assertEqual(store.observe(fixture(run, 1, status, status))["classification"], "accepted")
            self.assertEqual(store.observe(fixture(run, 1, "passed", "contradiction"))["classification"], "conflict")
            self.assertEqual(store.observe(fixture(run, 1, "failed", "failed"))["classification"], "duplicate")
            self.assertEqual(store.observation(run, run + ":gate-1", HEADS[0])["status"], "failed")
            self.assertEqual(store.observation(run, run + ":gate-2", HEADS[1])["status"], "unknown")
            restored = FixtureStore(Path(root) / "journal.jsonl")
            self.assertEqual(restored.snapshot(run)["state"], "crashed")
            self.assertEqual(restored.observe(fixture(run, 1, "passed", "late"))["classification"], "inactive")

    def test_assessment_rejects_additional_invocation_wrong_graph_or_stale_decision(self):
        run = "exp123-S1-success"
        base = {"run_id": run, "state": "completed", "events": [
            {"kind": "graph_started", "graph_id": "graph", "sequence": 1},
            {"kind": "agent_invoked", "node_id": "Agent1", "graph_id": "graph",
             "head_sha": HEADS[0], "invocation_id": "one"},
            {"kind": "gate_decided", "node_id": "Gate1", "graph_id": "graph",
             "gate_id": run + ":gate-1", "head_sha": HEADS[0],
             "source_check_id": run + ":check-1", "status": "passed"},
            {"kind": "terminal_result", "node_id": "Result1", "graph_id": "graph", "status": "passed"}]}
        assess("success", base)
        flow = b'{"synthetic_control":true}\n'
        base["events"][0]["graph_sha256"] = hashlib.sha256(flow).hexdigest()
        for index, row in enumerate(base["events"], 1):
            row["sequence"] = index
            row["run_id"] = run
        journal = b"\n".join(json.dumps(row).encode() for row in base["events"]) + b"\n"
        cases = {"success": {"raw": base, "assessment": assess("success", base)}}
        validate_capture(cases, journal, {"success": flow})
        with self.assertRaisesRegex(AssertionError, "flow_snapshot_mismatch"):
            validate_capture(cases, journal, {"success": b"changed"})
        with self.assertRaisesRegex(AssertionError, "journal_snapshot_mismatch"):
            validate_capture(cases, journal.replace(b"Agent1", b"Other1"), {"success": flow})
        for mutation in ("extra_agent", "wrong_graph", "stale_head", "invented_terminal"):
            changed = deepcopy(base)
            if mutation == "extra_agent":
                changed["events"].append(deepcopy(changed["events"][1]))
            elif mutation == "wrong_graph":
                changed["events"][2]["graph_id"] = "other"
            elif mutation == "stale_head":
                changed["events"][2]["head_sha"] = HEADS[1]
            else:
                changed["events"][3]["status"] = "failed"
            with self.assertRaises(AssertionError, msg=mutation):
                assess("success", changed)


if __name__ == "__main__":
    unittest.main()
