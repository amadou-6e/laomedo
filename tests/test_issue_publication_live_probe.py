"""No-network checks for EXP-15 exact matching and repeat-write guard."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


PATH = (Path(__file__).resolve().parents[1] / "experiments" /
        "issue-integration" / "45" / "live_probe.py")
SPEC = importlib.util.spec_from_file_location("exp15_probe", PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class LiveProbeTests(unittest.TestCase):
    def test_marker_is_exact_and_excludes_prs(self):
        items = [{"number": 1, "id": 11, "body": "EXP15-MARKER: exp15-abc"},
                 {"number": 2, "id": 12, "body": "EXP15-MARKER: exp15-abcx"},
                 {"number": 3, "id": 13, "body": "EXP15-MARKER: exp15-abc",
                  "pull_request": {"url": "https://example.invalid"}}]
        self.assertEqual([{"number": 1, "id": 11}],
                         probe.exact_matches(items, "exp15-abc"))

    def test_existing_evidence_prevents_repost(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            path.write_text("{}", encoding="utf-8")
            with patch.object(probe, "create") as create:
                with self.assertRaises(FileExistsError):
                    probe.run(path)
            create.assert_not_called()

    def test_suppressed_ack_is_not_exposed_to_caller(self):
        with patch.object(probe.subprocess, "run") as call:
            self.assertIsNone(probe.create("test", "marker", True))
        self.assertEqual(probe.subprocess.DEVNULL,
                         call.call_args.kwargs["stdout"])


if __name__ == "__main__":
    unittest.main()
