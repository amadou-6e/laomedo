"""Source integrity controls; generated records do not establish real acceptance."""

import hashlib
from pathlib import Path
import tempfile
import unittest

from session_retro.errors import RetrospectiveError
from session_retro.reader import SessionReader
from session_retro.settings import Settings
from support.utils import meta, record


class SourceTests(unittest.TestCase):
    """Each test owns a fresh source; no active user session is modified."""

    def setUp(self):
        """Create fresh owned temporary source and output paths."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name, "source.jsonl")
        self.settings = Settings(chunk_bytes=1024, max_record_bytes=1024)

    def test_byte_ranges_hashes_long_line_and_incomplete_tail(self):
        """Byte ranges hashes long line and incomplete tail."""
        parts = [
            meta(),
            record(
                "response_item",
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "text": "ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â‚¬Å¾Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡"
                        }
                    ],
                },
            ),
            b"x" * 5000 + b"\n",
            b'{"unfinished":',
        ]
        self.path.write_bytes(b"".join(parts))
        reader = SessionReader(self.path, self.settings)
        snapshot = reader.snapshot("internal-session")
        records = list(reader.records(snapshot))
        self.assertEqual(len(records), 3)
        self.assertIsNone(records[2].data)
        offset = 0
        for item, raw in zip(records, parts):
            self.assertEqual(item.locator.offset, offset)
            self.assertEqual(item.locator.length, len(raw))
            self.assertEqual(item.locator.sha256, hashlib.sha256(raw).hexdigest())
            offset += len(raw)

    def test_append_does_not_change_admitted_boundary_or_lock_writer(self):
        """Append does not change admitted boundary or lock writer."""
        self.path.write_bytes(meta())
        reader = SessionReader(self.path, self.settings)
        snapshot = reader.snapshot("internal-session")
        iterator = reader.records(snapshot)
        self.assertEqual(next(iterator).locator.line, 1)
        with self.path.open("ab") as writer:
            writer.write(
                record("event_msg", {"type": "user_message", "message": "later"})
            )
        self.assertEqual(list(iterator), [])
        self.assertLess(snapshot.boundary, self.path.stat().st_size)

    def test_identity_and_prefix_mutation_refuse(self):
        """Identity and prefix mutation refuse."""
        self.path.write_bytes(meta())
        reader = SessionReader(self.path, self.settings)
        snapshot = reader.snapshot("internal-session")
        row = next(reader.records(snapshot))
        snapshot.indexed_bytes = row.locator.length
        snapshot.sha256 = row.locator.prefix_sha256
        self.path.write_bytes(
            self.path.read_bytes().replace(b"internal-session", b"external-session")
        )
        with self.assertRaisesRegex(RetrospectiveError, "source_prefix_changed"):
            reader.verify(snapshot)
        with self.assertRaisesRegex(RetrospectiveError, "session_identity_mismatch"):
            reader.snapshot("internal-session")

    def test_replacement_and_truncation_refuse(self):
        """Replacement and truncation refuse."""
        self.path.write_bytes(meta())
        reader = SessionReader(self.path, self.settings)
        snapshot = reader.snapshot("internal-session")
        self.path.rename(self.path.with_suffix(".old"))
        self.path.write_bytes(meta())
        with self.assertRaisesRegex(RetrospectiveError, "source_replaced"):
            list(reader.records(snapshot))
        snapshot = reader.snapshot("internal-session")
        self.path.write_bytes(b"{}\n")
        with self.assertRaisesRegex(RetrospectiveError, "source_truncated"):
            list(reader.records(snapshot))
