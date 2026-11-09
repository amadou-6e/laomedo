"""Transactional, semantic and privacy internal controls for the local index."""

from pathlib import Path
import sqlite3
import tempfile
import unittest

from session_retro.errors import RetrospectiveError
from session_retro.index import SessionIndex
from session_retro.settings import Settings
from support.utils import meta, record


class IndexTests(unittest.TestCase):
    """Use private temporary paths and explicit internal session identities."""

    def setUp(self):
        """Create fresh owned temporary source and output paths."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = Path(self.root, "source.jsonl")
        self.database = Path(self.root, "private/index.sqlite")
        self.settings = Settings(
            private_root=Path(self.root, "private"),
            chunk_bytes=1024,
            max_record_bytes=2048,
            batch_records=2,
            search_characters=128,
            read_characters=128,
        )

    def test_resume_extend_pairing_and_full_source_retrieval(self):
        """Resume extend pairing and full source retrieval."""
        rows = [
            meta(),
            record(
                "response_item",
                {
                    "type": "custom_tool_call",
                    "call_id": "c1",
                    "name": "exec",
                    "input": "inspect",
                },
            ),
            record(
                "response_item",
                {
                    "type": "custom_tool_call_output",
                    "call_id": "c1",
                    "output": "Process exited with code 1\n",
                },
            ),
            record(
                "response_item",
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"text": "begin " + "x" * 180 + " ending"}],
                },
            ),
            record("compacted", {"message": "summary"}),
            b"{bad}\n",
            b"not-finished",
        ]
        self.source.write_bytes(b"".join(rows))
        index = SessionIndex(self.database, self.settings, create=True)
        partial = index.build(self.source, "internal-session", stop_after=2)
        self.assertFalse(partial.snapshot.complete)
        index.close()
        index = SessionIndex(self.database, self.settings, create=True)
        self.addCleanup(index.close)
        result = index.build(self.source, "internal-session")
        self.assertTrue(result.snapshot.complete)
        self.assertEqual(result.snapshot.lines, 6)
        self.assertEqual(result.snapshot.trailing_bytes, len(rows[-1]))
        self.assertEqual(index.coverage().paired_call_ids, 1)
        self.assertEqual(index.coverage().explicit_failure_records, 0)
        self.assertEqual(index.coverage().result_outcomes_unknown, 1)
        self.assertEqual(index.coverage().kinds["malformed"], 1)
        self.assertEqual(index.coverage().kinds["compaction"], 1)
        hit = index.search("begin")[0]
        self.assertTrue(hit.text_truncated)
        page = index.read(hit.line)
        self.assertEqual(page.next_start, 128)
        self.assertTrue(index.read(hit.line, start=128).text.endswith("ending"))
        with self.source.open("ab") as stream:
            stream.write(
                b"\n" + record("event_msg", {"type": "user_message", "message": "new"})
            )
        index.build(self.source, "internal-session", extend=True)
        self.assertEqual(index.snapshot().lines, 8)
        self.assertEqual(index.snapshot().trailing_bytes, 0)
        self.assertTrue(index.verify().verified)

    def test_redaction_outcome_unknown_and_safe_database_admission(self):
        """Redaction outcome unknown and safe database admission."""
        secret = "ghp_" + "A" * 32
        self.source.write_bytes(
            meta()
            + record(
                "response_item",
                {
                    "type": "function_call_output",
                    "call_id": "missing",
                    "output": "normal text mentioning error " + secret,
                },
            )
        )
        index = SessionIndex(self.database, self.settings, create=True)
        self.addCleanup(index.close)
        index.build(self.source, "internal-session")
        self.assertEqual(index.coverage().explicit_failure_records, 0)
        self.assertEqual(index.coverage().ambiguous_or_unpaired_call_ids, 1)
        self.assertNotIn(secret, index.read(2).text)
        self.assertEqual(index.search(secret), [])
        with self.assertRaisesRegex(
            RetrospectiveError, "database_outside_private_root"
        ):
            SessionIndex(Path(self.root, "outside.sqlite"), self.settings, create=True)
        other = Path(self.root, "private/other.sqlite")
        with sqlite3.connect(other) as connection:
            connection.execute("CREATE TABLE unrelated(value)")
        connection.close()
        original = other.read_bytes()
        with self.assertRaisesRegex(RetrospectiveError, "database_not_owned"):
            SessionIndex(other, self.settings, create=True)
        self.assertEqual(other.read_bytes(), original)

    def test_source_change_prevents_resume_and_read(self):
        """Source change prevents resume and read."""
        self.source.write_bytes(
            meta() + record("event_msg", {"type": "user_message", "message": "before"})
        )
        index = SessionIndex(self.database, self.settings, create=True)
        self.addCleanup(index.close)
        index.build(self.source, "internal-session")
        self.source.write_bytes(self.source.read_bytes().replace(b"before", b"after!"))
        with self.assertRaisesRegex(RetrospectiveError, "source_record_changed"):
            index.read(2)
        with self.assertRaisesRegex(RetrospectiveError, "source_prefix_changed"):
            index.build(self.source, "internal-session")
