"""Private report controls; native context is not silently counted as a task."""

import json
from pathlib import Path
import tempfile
import unittest

from session_retro.errors import RetrospectiveError
from session_retro.episodes import EpisodeBuilder
from session_retro.index import SessionIndex
from session_retro.report import RetrospectiveReport
from session_retro.settings import Settings
from support.utils import meta, record


class ReportTests(unittest.TestCase):
    """Own temporary evidence and verify semantic categories rather than wording."""

    def test_existing_report_source_and_outside_output_are_preserved(self):
        """Refuse regeneration before a report can truncate its own source."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "report"
            target.mkdir()
            source = target / "episodes.jsonl"
            original = meta()
            source.write_bytes(original)
            sentinel = target / "README.md"
            sentinel.write_text("existing evidence", encoding="utf-8")
            index = SessionIndex(
                root / "index.sqlite", Settings(private_root=root), create=True
            )
            try:
                index.build(source, "internal-session")
                with self.assertRaisesRegex(
                    RetrospectiveError, "report_destination_exists"
                ):
                    RetrospectiveReport(index).write(target)
                with self.assertRaises(FileExistsError):
                    EpisodeBuilder(index).write(source)
                with self.assertRaisesRegex(
                    RetrospectiveError, "report_outside_private_root"
                ):
                    EpisodeBuilder(index).write(root.parent / "outside.jsonl")
                self.assertEqual(source.read_bytes(), original)
                self.assertEqual(sentinel.read_text(), "existing evidence")
                index.verify()
            finally:
                index.close()

    def test_many_native_types_and_finals_keep_explicit_bounded_summaries(self):
        """A long window and arbitrary native types must not grow Python lists."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            source.write_bytes(
                meta()
                + record(
                    "response_item", {"type": "message", "role": "user", "content": []}
                )
                + b"".join(
                    record(
                        "response_item",
                        {
                            "type": "message",
                            "role": "assistant",
                            "phase": "final_answer",
                            "content": [],
                        },
                    )
                    + record(f"extension-{number}", {})
                    for number in range(12)
                )
            )
            index = SessionIndex(
                root / "index.sqlite",
                Settings(private_root=root, page_records=2),
                create=True,
            )
            try:
                index.build(source, "internal-session")
                result = RetrospectiveReport(index).write(root / "report")
                episode = json.loads(
                    (Path(result.directory) / "episodes.jsonl").read_text()
                )
                self.assertEqual(len(episode["final_answer_lines"]), 2)
                self.assertEqual(episode["omitted_final_answer_lines"], 10)
                coverage = index.coverage()
                self.assertEqual(len(coverage.types), 2)
                self.assertEqual(coverage.omitted_native_types, 12)
            finally:
                index.close()

    def test_context_windows_and_final_phase_are_distinct(self):
        """Preserve context, commentary and finals while keeping analysis pending."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            source.write_bytes(
                meta()
                + record(
                    "response_item",
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"text": "<environment_context>test</environment_context>"}
                        ],
                    },
                )
                + record(
                    "response_item",
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"text": "fix this"}],
                    },
                )
                + record(
                    "response_item",
                    {
                        "type": "message",
                        "role": "assistant",
                        "phase": "commentary",
                        "content": [{"text": "checking"}],
                    },
                )
                + record(
                    "response_item",
                    {
                        "type": "message",
                        "role": "assistant",
                        "phase": "final_answer",
                        "content": [{"text": "done"}],
                    },
                )
            )
            index = SessionIndex(
                root / "private/index.sqlite",
                Settings(private_root=root / "private"),
                create=True,
            )
            try:
                index.build(source, "internal-session")
                report = RetrospectiveReport(index).write(root / "private/report")
                episodes = [
                    json.loads(x)
                    for x in (root / "private/report/episodes.jsonl")
                    .read_text()
                    .splitlines()
                ]
                self.assertEqual(report.episodes, 2)
                self.assertEqual(episodes[0]["source_kind"], "injected_context")
                self.assertEqual(episodes[1]["final_answer_lines"], [5])
                self.assertEqual(index.coverage().analyzed_records, 0)
                with self.assertRaisesRegex(
                    RetrospectiveError, "report_outside_private_root"
                ):
                    RetrospectiveReport(index).write(root / "outside")
                index.db.execute("UPDATE events SET offset=offset+1 WHERE line=3")
                index.db.commit()
                with self.assertRaisesRegex(
                    RetrospectiveError, "index_locator_integrity_failed"
                ):
                    index.coverage()
            finally:
                index.close()
