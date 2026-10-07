"""Run the frozen EXP-108 synthetic controls in the installed-wheel CI suite."""

import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Exp108CI(unittest.TestCase):
    def test_connection_controls_without_rewriting_evidence(self):
        probe = ROOT / "experiments" / "exp108" / "probe.py"
        observation = probe.with_name("observation-v2.json")
        before = observation.read_bytes()
        result = subprocess.run([sys.executable, str(probe)], cwd=ROOT,
                                capture_output=True, text=True, timeout=15,
                                check=True)
        summary = json.loads(result.stdout)
        self.assertEqual(summary, {"passed": True, "cases": 24,
                                   "synthetic_only": True})
        self.assertEqual(observation.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
