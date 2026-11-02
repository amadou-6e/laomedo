"""Direct internal browser-harness startup controls without launching services."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class BrowserEntrypointTests(unittest.TestCase):
    def test_direct_help_works_outside_checkout_without_a_tests_pythonpath(self):
        environment = {
            k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}
        }
        for name in (
            "serve.py",
            "prepare.py",
        ):
            with self.subTest(script=name), tempfile.TemporaryDirectory() as cwd:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(Path(__file__).with_name(name)),
                        "--help",
                    ],
                    cwd=cwd,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--manifest", result.stdout)
