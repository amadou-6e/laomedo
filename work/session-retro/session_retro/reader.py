"""Finite shared-read JSONL ranges with bounded oversized-record handling."""

import hashlib
import json
import os
from pathlib import Path

from session_retro.errors import RetrospectiveError
from session_retro.models import RecordLocator, SourceRecord, SourceSnapshot
from session_retro.settings import PARSER_VERSION, Settings
from session_retro.utils import open_source


class SessionReader:
    """Read one explicitly selected native session without changing its source.

    Parameters
    ----------
    path : Path
        Original session selected by the user.
    settings : Settings
        Injected resource bounds and interpretation fingerprint.
    """

    def __init__(self, path: Path, settings: Settings):
        """Retain the selected canonical path and injected scan limits."""
        self.path = path.resolve()
        self.settings = settings

    def snapshot(self, session_id: str) -> SourceSnapshot:
        """Validate native identity before admitting a finite source boundary."""
        with open_source(self.path) as stream:
            stat = os.fstat(stream.fileno())
            first = stream.readline(self.settings.max_record_bytes + 1)
            try:
                meta = json.loads(first)
            except (ValueError, UnicodeDecodeError):
                raise RetrospectiveError("invalid_session_metadata") from None
            if (
                meta.get("type") != "session_meta"
                or meta.get("payload", {}).get("id") != session_id
            ):
                raise RetrospectiveError("session_identity_mismatch")
            return SourceSnapshot(
                path=str(self.path),
                session_id=session_id,
                identity=self._identity(stat),
                boundary=stat.st_size,
                sha256=hashlib.sha256().hexdigest(),
                parser_version=PARSER_VERSION,
                settings_digest=self.settings.digest(),
            )

    def records(self, snapshot: SourceSnapshot):
        """Yield complete source records and bounded bytes; ignore append suffixes.

        Verify the prior committed prefix before resuming. A trailing incomplete
        record is never yielded; its range remains visible in coverage.
        """
        with open_source(self.path) as stream:
            self._check_identity(stream, snapshot)
            prefix = self._hash(stream, snapshot.indexed_bytes)
            if prefix.hexdigest() != snapshot.sha256:
                raise RetrospectiveError("source_prefix_changed")
            offset, line = snapshot.indexed_bytes, snapshot.lines + 1
            record_hash = hashlib.sha256()
            buffer = bytearray()
            length = 0
            oversized = False
            remaining = snapshot.boundary - snapshot.indexed_bytes
            while remaining:
                block = stream.read(min(remaining, self.settings.chunk_bytes))
                if not block:
                    raise RetrospectiveError("source_truncated")
                remaining -= len(block)
                start = 0
                while start < len(block):
                    end = block.find(b"\n", start)
                    finish = len(block) if end < 0 else end + 1
                    piece = memoryview(block)[start:finish]
                    prefix.update(piece)
                    record_hash.update(piece)
                    length += len(piece)
                    if not oversized:
                        if length > self.settings.max_record_bytes:
                            oversized = True
                            buffer.clear()
                        else:
                            buffer.extend(piece)
                    if end >= 0:
                        locator = RecordLocator(
                            line=line,
                            offset=offset,
                            length=length,
                            sha256=record_hash.hexdigest(),
                            prefix_sha256=prefix.hexdigest(),
                        )
                        yield SourceRecord(
                            locator=locator, data=None if oversized else bytes(buffer)
                        )
                        offset += length
                        line += 1
                        length = 0
                        oversized = False
                        buffer.clear()
                        record_hash = hashlib.sha256()
                    start = finish
            self._check_identity(stream, snapshot)

    def verify(self, snapshot: SourceSnapshot) -> None:
        """Re-read the committed prefix and reject source mutation or replacement."""
        with open_source(self.path) as stream:
            self._check_identity(stream, snapshot)
            if (
                self._hash(stream, snapshot.indexed_bytes).hexdigest()
                != snapshot.sha256
            ):
                raise RetrospectiveError("source_prefix_changed")

    def read(self, snapshot: SourceSnapshot, locator: RecordLocator) -> bytes:
        """Return a bounded exact record only after identity, range and hash checks."""
        if locator.length > self.settings.max_record_bytes:
            raise RetrospectiveError("record_requires_bounded_large_payload_decoder")
        if locator.offset + locator.length > snapshot.indexed_bytes:
            raise RetrospectiveError("record_outside_indexed_prefix")
        with open_source(self.path) as stream:
            self._check_identity(stream, snapshot)
            stream.seek(locator.offset)
            data = stream.read(locator.length)
            if hashlib.sha256(data).hexdigest() != locator.sha256:
                raise RetrospectiveError("source_record_changed")
            return data

    def _identity(self, stat) -> str:
        """Use the open file's native identity, not modification time or size."""
        return f"{stat.st_dev}:{stat.st_ino}"

    def _check_identity(self, stream, snapshot: SourceSnapshot) -> None:
        """Require both the current path and held handle to identify this source."""
        held, current = os.fstat(stream.fileno()), self.path.stat()
        if (
            self._identity(held) != snapshot.identity
            or self._identity(current) != snapshot.identity
        ):
            raise RetrospectiveError("source_replaced")
        if held.st_size < snapshot.boundary or current.st_size < snapshot.boundary:
            raise RetrospectiveError("source_truncated")

    def _hash(self, stream, length: int):
        """Consume exactly length bytes in fixed buffers and return running SHA256."""
        digest = hashlib.sha256()
        while length:
            part = stream.read(min(length, self.settings.chunk_bytes))
            if not part:
                raise RetrospectiveError("source_truncated")
            digest.update(part)
            length -= len(part)
        return digest
