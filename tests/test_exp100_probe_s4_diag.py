"""Run S4-02's source-tree safety tests from installed-wheel CI."""

from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Exp100S4DiagnosticCI(unittest.TestCase):
    def test_no_docker_probe_guards(self):
        result = subprocess.run(
            [sys.executable, "-m", "unittest",
             "experiments.exp100.test_probe_s4_diag", "-q"],
            cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
