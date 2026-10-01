"""Private rollout export stays within the native sessions tree."""

import json
from pathlib import Path
import tempfile
import unittest

from laomedo.local_runner import RunnerError
from laomedo.rollout_export import export_rollout


class Result:
    def __init__(self, stdout):
        self.stdout = stdout


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "private-state"
        self.run_id = "b305a7bd-0ea9-40eb-b4ef-34dbef4fd4a4"
        self.thread = "c61de4af-35cc-4e25-9dd6-73cc9acdf9d5"
        self.run_dir = self.state / "runs" / self.run_id
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "record.json").write_text(json.dumps({
            "run_id": self.run_id, "thread_id": self.thread}))

    def test_exact_session_only(self):
        calls = []

        def docker(args, **kwargs):
            calls.append(args)
            if "find" in args:
                path = f"/home/runner/.codex/sessions/2026/10/01/rollout-{self.thread}.jsonl\n"
                return Result(path.encode())
            return Result(b'{"type":"session_meta"}\n')

        output = export_rollout(self.state, self.run_id, docker_run=docker)
        self.assertEqual(output.read_bytes(), b'{"type":"session_meta"}\n')
        self.assertEqual(len(calls), 2)
        self.assertIn("readonly", " ".join(calls[0]))
        self.assertNotIn("auth.json", " ".join(calls[1]))

    def test_refuses_path_outside_sessions(self):
        def docker(args, **kwargs):
            return Result(b"/home/runner/.codex/auth.json\n")

        with self.assertRaisesRegex(RunnerError, "native_rollout_path_invalid"):
            export_rollout(self.state, self.run_id, docker_run=docker)
        self.assertFalse((self.run_dir / "native-rollout.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
