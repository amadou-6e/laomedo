"""Meaningful fail-closed checks for runtime scaffold materialization."""

from pathlib import Path
import tempfile
import unittest

from materialize_candidate import materialize


class MaterializeCandidateTests(unittest.TestCase):
    def test_only_empty_known_runtime_directories_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            raw = root / "draft"
            raw.mkdir()
            (raw / "SKILL.md").write_text("synthetic", encoding="utf-8")
            for directory in (".agents", ".codex", ".git"):
                (raw / directory).mkdir()
            candidate = root / "candidate"
            self.assertEqual(materialize(raw, candidate, root),
                             [".agents", ".codex", ".git"])
            self.assertEqual((candidate / "SKILL.md").read_text(), "synthetic")
            self.assertEqual([path.name for path in candidate.iterdir()], ["SKILL.md"])

    def test_nonempty_runtime_directory_is_rejected_without_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            raw = root / "draft"
            (raw / ".codex").mkdir(parents=True)
            (raw / "SKILL.md").write_text("synthetic", encoding="utf-8")
            (raw / ".codex" / "auth.json").write_text("synthetic", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "runtime_directory_not_empty"):
                materialize(raw, root / "candidate", root)
            self.assertFalse((root / "candidate").exists())

    def test_unapproved_file_is_rejected_without_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            raw = root / "draft"
            raw.mkdir()
            (raw / "SKILL.md").write_text("synthetic", encoding="utf-8")
            (raw / "extra.sh").write_text("synthetic", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unapproved_raw_draft_entry"):
                materialize(raw, root / "candidate", root)
            self.assertFalse((root / "candidate").exists())


if __name__ == "__main__":
    unittest.main()
