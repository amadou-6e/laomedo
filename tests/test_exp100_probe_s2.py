"""Check EXP-100/S2 one-shot evidence behavior from installed-wheel CI."""

from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Exp100ProbeCI(unittest.TestCase):
    def test_failed_record_is_not_retried(self):
        result = subprocess.run(
            [sys.executable, "-m", "unittest",
             "experiments.exp100.test_probe_s2", "-q"],
            cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
