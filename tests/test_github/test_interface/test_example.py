"""Exercise the documented builder in a fresh interpreter, without a graph run."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path

from support.paths import repository_root


@unittest.skipUnless(
    find_spec("langflow"), "Optional Langflow runtime is not installed"
)
class GitHubExampleTests(unittest.TestCase):
    def test_documented_cli_builds_both_selected_resources_without_execution(self):
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            for kind in ("issue", "pr"):
                with self.subTest(kind=kind):
                    target = Path(directory) / f"{kind}.json"
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(root / "examples/github/build_flow.py"),
                            "--repository",
                            "example/selected-repository",
                            "--number",
                            "17",
                            "--title",
                            "Selected resource",
                            "--kind",
                            kind,
                            "--output",
                            str(target),
                        ],
                        cwd=root,
                        env={
                            **os.environ,
                            "LANGFLOW_CONFIG_DIR": str(Path(directory) / "runtime"),
                            "LFX_CONFIG_DIR": str(Path(directory) / "runtime"),
                        },
                        capture_output=True,
                        text=True,
                        timeout=90,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    flow = json.loads(target.read_text(encoding="utf-8"))
                    self.assertEqual(len(flow["data"]["nodes"]), 1)
                    self.assertEqual(flow["data"]["edges"], [])
                    template = flow["data"]["nodes"][0]["data"]["node"]["template"]
                    self.assertEqual(
                        template[kind + "_choice"]["value"], "#17 Selected resource"
                    )
