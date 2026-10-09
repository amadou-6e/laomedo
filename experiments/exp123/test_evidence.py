"""Read-only replay of the committed S1 bytes; never dispatch an experiment."""
import hashlib
import json
from pathlib import Path
import unittest
from experiments.exp123.probe import validate_capture


class EvidenceTests(unittest.TestCase):
    def test_captured_bytes_reconstruct_s1(self):
        root = Path(__file__).parent
        data = (root / "observation-s1.json").read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         "747466ac11396d62e7e2c995f44e54fff382bd50eaf7071b5255307f778abf49")
        report = json.loads(data)
        self.assertEqual(report["state"], "passed")
        self.assertTrue(report["capture_verified"])
        self.assertTrue(report["cleanup_verified"])
        evidence = root / "evidence" / "S1"
        self.assertEqual(len(report["evidence_hashes"]), 15)
        for filename, digest in report["evidence_hashes"].items():
            self.assertEqual(hashlib.sha256((evidence / filename).read_bytes()).hexdigest(), digest)
        flows = {name: (evidence / (name + ".flow.json")).read_bytes() for name in report["cases"]}
        validate_capture(report["cases"], (evidence / "journal.jsonl").read_bytes(), flows)
        for name, case in report["cases"].items():
            self.assertEqual(json.loads((evidence / (name + ".json")).read_bytes()), case["raw"])
            rows = case["raw"]["events"]
            if name in {"stop", "crash"}:
                self.assertEqual([row["classification"] for row in rows if row["kind"] == "delivery"], ["inactive"])
            else:
                terminal = next(row for row in rows if row["kind"] == "terminal_result")
                self.assertEqual(terminal["node_id"], "Result2" if name in {"repair", "cap"} else "Result1")
            if name in {"repair", "cap"}:
                selected = next(row for row in rows if row["kind"] == "branch_selected")
                second = next(row for row in rows if row["kind"] == "agent_invoked" and row["node_id"] == "Agent2")
                self.assertEqual(selected["chosen"], "failure")
                self.assertLess(selected["sequence"], second["sequence"])


if __name__ == "__main__":
    unittest.main()
