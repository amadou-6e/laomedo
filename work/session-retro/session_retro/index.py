"""Transactional local source index; bounded text is not a lossless transcript."""

import json
from pathlib import Path
import sqlite3
import time

from session_retro.decoder import CodexEventDecoder
from session_retro.errors import RetrospectiveError
from session_retro.memory import ProcessMemory
from session_retro.models import (
    BuildResult,
    CoverageReport,
    NormalizedEvent,
    ReadPage,
    RecordLocator,
    SearchHit,
    SourceRecord,
    SourceSnapshot,
    VerificationResult,
)
from session_retro.reader import SessionReader
from session_retro.settings import PARSER_VERSION, Settings


class SessionIndex:
    """Own one private database; never open another application database for writes."""

    def __init__(self, database: Path, settings: Settings, *, create: bool = False):
        """Admit an explicit private destination and refuse unrelated SQLite stores."""
        if settings.private_root is None:
            raise RetrospectiveError("private_root_required")
        self.path = database.resolve()
        self.settings = settings
        if not self.path.is_relative_to(settings.private_root.resolve()):
            raise RetrospectiveError("database_outside_private_root")
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        elif not self.path.is_file():
            raise RetrospectiveError("index_missing")
        self.db = sqlite3.connect(
            self.path if create else self.path.as_uri() + "?mode=ro", uri=not create
        )
        self.db.row_factory = sqlite3.Row
        app = self.db.execute("PRAGMA application_id").fetchone()[0]
        existing = self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        if app != 0x5254524F and (app or existing):
            self.db.close()
            raise RetrospectiveError("database_not_owned")
        if create:
            self.db.executescript("""
                PRAGMA application_id=1381257807;
                PRAGMA journal_mode=WAL;
                PRAGMA cache_size=-8192;
                CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    line INTEGER PRIMARY KEY, offset INTEGER NOT NULL, length INTEGER NOT NULL,
                    sha256 TEXT NOT NULL, prefix_sha256 TEXT NOT NULL, timestamp TEXT,
                    native_type TEXT NOT NULL, kind TEXT NOT NULL, role TEXT,
                    call_id TEXT, turn_id TEXT, name TEXT, failure INTEGER,
                    text TEXT NOT NULL, text_truncated INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS call_lookup ON events(call_id,kind);
                CREATE INDEX IF NOT EXISTS kind_lookup ON events(kind,line);
            """)

    def close(self) -> None:
        """Release only this index connection; source files are independently owned."""
        self.db.close()

    def snapshot(self) -> SourceSnapshot:
        """Read the durable checkpoint; reject a database without admitted source."""
        row = self.db.execute("SELECT value FROM state WHERE id=1").fetchone()
        if row is None:
            raise RetrospectiveError("index_not_initialized")
        return SourceSnapshot.model_validate_json(row[0])

    def build(
        self,
        source: Path,
        session_id: str,
        *,
        extend: bool = False,
        stop_after: int | None = None,
    ) -> BuildResult:
        """Index/resume complete records, atomically retaining each committed cursor."""
        started = time.perf_counter()
        if source.resolve() == self.path:
            raise RetrospectiveError("source_is_database")
        reader = SessionReader(source, self.settings)
        admitted = reader.snapshot(session_id)
        row = self.db.execute("SELECT value FROM state WHERE id=1").fetchone()
        snapshot = SourceSnapshot.model_validate_json(row[0]) if row else admitted
        if (
            snapshot.path != admitted.path
            or snapshot.session_id != session_id
            or snapshot.identity != admitted.identity
        ):
            raise RetrospectiveError("index_source_mismatch")
        if (
            snapshot.parser_version != PARSER_VERSION
            or snapshot.settings_digest != self.settings.digest()
        ):
            raise RetrospectiveError("index_settings_changed")
        reader.verify(snapshot)
        if extend:
            snapshot.boundary = admitted.boundary
            snapshot.complete = False
        if snapshot.complete:
            return BuildResult(
                snapshot=snapshot,
                elapsed_seconds=time.perf_counter() - started,
                peak_rss_bytes=ProcessMemory.peak(),
            )
        snapshot.complete = False
        self._save(snapshot)
        self.db.commit()
        decoder = CodexEventDecoder(self.settings)
        last_turn = self.db.execute(
            "SELECT turn_id FROM events WHERE turn_id IS NOT NULL ORDER BY line DESC LIMIT 1"
        ).fetchone()
        decoder.turn_id = last_turn[0] if last_turn else None
        count = 0
        for record in reader.records(snapshot.model_copy()):
            event = decoder.decode(record)
            self._insert(event)
            snapshot.indexed_bytes = record.locator.offset + record.locator.length
            snapshot.lines = record.locator.line
            snapshot.sha256 = record.locator.prefix_sha256
            count += 1
            if count % self.settings.batch_records == 0:
                self._save(snapshot)
                self.db.commit()
            if stop_after is not None and count >= stop_after:
                self._save(snapshot)
                self.db.commit()
                return BuildResult(
                    snapshot=snapshot,
                    elapsed_seconds=time.perf_counter() - started,
                    peak_rss_bytes=ProcessMemory.peak(),
                )
        snapshot.trailing_bytes = snapshot.boundary - snapshot.indexed_bytes
        self._save(snapshot)
        self.db.commit()
        reader.verify(snapshot)
        snapshot.complete = True
        self._save(snapshot)
        self.db.commit()
        return BuildResult(
            snapshot=snapshot,
            elapsed_seconds=time.perf_counter() - started,
            peak_rss_bytes=ProcessMemory.peak(),
        )

    def coverage(self) -> CoverageReport:
        """Reconcile physical source records and explicit gaps; no analysis claim."""
        snapshot = self.snapshot()
        counts = {
            r[0]: r[1]
            for r in self.db.execute("SELECT kind,COUNT(*) FROM events GROUP BY kind")
        }
        pairs = self.db.execute(
            "SELECT COUNT(*) FROM (SELECT call_id FROM events WHERE call_id IS NOT NULL AND kind IN ('call','result') GROUP BY call_id HAVING SUM(kind='call')=1 AND SUM(kind='result')=1)"
        ).fetchone()[0]
        unpaired = self.db.execute(
            "SELECT COUNT(*) FROM (SELECT call_id FROM events WHERE call_id IS NOT NULL AND kind IN ('call','result') GROUP BY call_id HAVING SUM(kind='call')!=1 OR SUM(kind='result')!=1)"
        ).fetchone()[0]
        return CoverageReport(
            snapshot=snapshot,
            records=sum(counts.values()),
            kinds=counts,
            paired_call_ids=pairs,
            ambiguous_or_unpaired_call_ids=unpaired,
            calls_without_id=self.db.execute(
                "SELECT COUNT(*) FROM events WHERE kind IN ('call','result') AND call_id IS NULL"
            ).fetchone()[0],
            explicit_failure_records=self.db.execute(
                "SELECT COUNT(*) FROM events WHERE failure=1"
            ).fetchone()[0],
            truncated_search_records=self.db.execute(
                "SELECT COUNT(*) FROM events WHERE text_truncated=1"
            ).fetchone()[0],
            types=dict(
                self.db.execute(
                    "SELECT native_type,COUNT(*) FROM events GROUP BY native_type"
                )
            ),
        )

    def search(
        self, query: str, *, after: int = 0, kind: str | None = None
    ) -> list[SearchHit]:
        """Return a bounded page of literal matches; results are candidate evidence."""
        rows = self.db.execute(
            "SELECT line,timestamp,kind,role,name,call_id,offset,length,text,text_truncated FROM events WHERE line>? AND instr(lower(text),lower(?))>0 AND (? IS NULL OR kind=?) ORDER BY line LIMIT ?",
            (after, query, kind, kind, self.settings.page_records),
        )
        return [SearchHit(**dict(row)) for row in rows]

    def read(self, line: int, *, start: int = 0) -> ReadPage:
        """Re-read exact verified source and page extracted text, not cached snippets."""
        row = self.db.execute("SELECT * FROM events WHERE line=?", (line,)).fetchone()
        if row is None or start < 0:
            raise RetrospectiveError("invalid_record_page")
        locator = RecordLocator(**{k: row[k] for k in RecordLocator.model_fields})
        snapshot = self.snapshot()
        data = SessionReader(Path(snapshot.path), self.settings).read(snapshot, locator)
        event = CodexEventDecoder(self.settings).decode(
            SourceRecord(locator=locator, data=data), full_text=True
        )
        if start > len(event.text):
            raise RetrospectiveError("invalid_record_page")
        end = min(len(event.text), start + self.settings.read_characters)
        return ReadPage(
            line=line,
            native_type=event.native_type,
            text=event.text[start:end],
            start=start,
            next_start=end if end < len(event.text) else None,
            total_characters=len(event.text),
        )

    def verify(self) -> VerificationResult:
        """Verify all indexed source bytes without parsing or model execution."""
        snapshot = self.snapshot()
        SessionReader(Path(snapshot.path), self.settings).verify(snapshot)
        return VerificationResult(
            verified=True, bytes=snapshot.indexed_bytes, sha256=snapshot.sha256
        )

    def _save(self, snapshot: SourceSnapshot) -> None:
        """Update one checkpoint inside the same transaction as its indexed rows."""
        self.db.execute(
            "INSERT OR REPLACE INTO state VALUES(1,?)", (snapshot.model_dump_json(),)
        )

    def _insert(self, event: NormalizedEvent) -> None:
        """Persist only bounded normalized values and exact original locators."""
        loc = event.locator
        self.db.execute(
            "INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                loc.line,
                loc.offset,
                loc.length,
                loc.sha256,
                loc.prefix_sha256,
                event.timestamp,
                event.native_type,
                event.kind,
                event.role,
                event.call_id,
                event.turn_id,
                event.name,
                event.failure,
                event.text,
                int(event.text_truncated),
            ),
        )
