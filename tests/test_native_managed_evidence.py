"""Read-only committed S12 capture integrity, not a new experiment."""
from hashlib import sha256
import json
from pathlib import Path
import unittest
from experiments.exp104.native_managed_checks import validate

ROOT = Path(__file__).resolve().parents[1] / "experiments/exp104"


class NativeManagedEvidenceTests(unittest.TestCase):
    def test_original_files_and_journal_derived_mutations(self):
        pins = {
            "native-managed-s12-a-observation.json": "c3f2f57597abbafb0f1814378bf2aaf65585c76d6b74f344e2ba6db1bb75f220",
            "native-managed-s12-b-observation.json": "e80b5afa08d6077d154807a23ed7f57ab0d7994e47c7700f84faaf26c594bff4",
            "native-managed-s12-b-provider-attempts.jsonl": "cee7d437a24955f0d13b5d33a6fd270771b3e4415690dbbd0731a3478d6ae7df",
        }
        for name, digest in pins.items():
            with self.subTest(name=name):
                self.assertEqual(sha256((ROOT / name).read_bytes()).hexdigest(), digest)
        value = json.loads((ROOT / "native-managed-s12-b-observation.json").read_bytes())
        journal = [json.loads(line) for line in
                   (ROOT / "native-managed-s12-b-provider-attempts.jsonl").read_bytes().splitlines()]
        self.assertEqual(len(journal), 8)
        self.assertEqual(value["provider_mutations"],
                         [event for event in journal if event["operation"] in {"git_push", "pr_create", "pr_update", "issue_create"}])
        self.assertTrue(validate(value))
        self.assertAlmostEqual(value["loss"]["revoked"] - value["loss"]["kill_completed"], 4.985, places=3)
        self.assertGreater(value["loss"]["b_create_intent_monotonic"], value["loss"]["denied"])
        first = json.loads((ROOT / "native-managed-s12-a-observation.json").read_bytes())
        self.assertEqual(first["result"], "incomplete")
        self.assertEqual(first["delivery"], {})
        self.assertEqual(first["provider_mutations"], [])
