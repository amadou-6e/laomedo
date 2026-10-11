"""Read-only S13 original evidence checks, never a new live run."""
from hashlib import sha256
import json
from pathlib import Path
import unittest
from experiments.exp104.native_localrunner_checks import validate

ROOT = Path(__file__).resolve().parents[1] / "experiments/exp104"


class LocalRunnerEvidenceTests(unittest.TestCase):
    def test_committed_originals_and_reconstructed_journal(self):
        files = {
            "native-localrunner-s13-a-observation.json": "9f2b0e04ad56eb52a6d84b9ca55fc4378552076a4f6bf939b2a992c64f09eeec",
            "native-localrunner-s13-a-provider-attempts.jsonl": "c21a24bc259a8fc08dd6dd6bc21c554b2087d4b08d47887092a1ec5cd8a166b6",
        }
        for name, digest in files.items():
            with self.subTest(name=name):
                self.assertEqual(sha256((ROOT / name).read_bytes()).hexdigest(), digest)
        value = json.loads((ROOT / "native-localrunner-s13-a-observation.json").read_bytes())
        journal = [json.loads(row) for row in (ROOT / "native-localrunner-s13-a-provider-attempts.jsonl").read_bytes().splitlines()]
        self.assertEqual(len(journal), 8)
        self.assertEqual(value["provider_mutations"], [row for row in journal
            if row["operation"] in {"git_push", "pr_create", "pr_update", "issue_create"}])
        self.assertTrue(validate(value))
        self.assertAlmostEqual(value["loss"]["revoked"] - value["loss"]["kill_completed"], 4.954, places=3)
        self.assertGreater(value["loss"]["b_create_intent_monotonic"], value["loss"]["denied"])
        self.assertEqual(value["source_sha"], "2bde4340717140b53b96da012d26428e632a4cae")
        for side in ("a", "b"):
            self.assertEqual(value["production"][side]["requests"], ["initialize"])
            self.assertEqual(value["production"][side]["model_turns"], 0)
        self.assertTrue(value["shared_ledger_unchanged"])
