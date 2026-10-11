"""Run the EXP-100/S2 source-tree probe from installed-wheel CI."""

from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Exp100BundleCI(unittest.TestCase):
    def test_credential_free_bundle_cases(self):
        result = subprocess.run(
            [sys.executable, "-m", "unittest",
             "experiments.exp100.test_bundle_transfer", "-q"],
            cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
