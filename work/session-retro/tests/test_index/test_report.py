"""Private report controls; native context is not silently counted as a task."""

import json
from pathlib import Path
import tempfile
import unittest

from session_retro.errors import RetrospectiveError
from session_retro.index import SessionIndex
from session_retro.report import RetrospectiveReport
from session_retro.settings import Settings
from support.utils import meta, record


class ReportTests(unittest.TestCase):
    """Own temporary evidence and verify semantic categories rather than wording."""

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
