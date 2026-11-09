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

    def snapshot(
        self, session_id: str, *, boundary: int | None = None
    ) -> SourceSnapshot:
        """Capture and admit a finite native session prefix.

        Parameters
        ----------
        session_id : str
            Expected native identity from the selected session.
        boundary : int, optional
            Earlier reproducible byte limit; otherwise capture current file length.

        Returns
        -------
        SourceSnapshot
            Identity, finite limit and empty-prefix hash; no semantic review claim.

        Raises
        ------
        RetrospectiveError
            Invalid metadata, identity mismatch or out-of-range boundary.
        OSError
            Source cannot be opened read-only.

        Notes
        -----
        Only reads the selected file; later appends are outside the captured limit.
        """
        with open_source(self.path) as stream:
            stat = os.fstat(stream.fileno())
            first = stream.readline(self.settings.max_record_bytes + 1)
            if not first.endswith(b"\n"):
                raise RetrospectiveError("invalid_session_metadata")
            try:
                meta = json.loads(first)
            except (ValueError, UnicodeDecodeError):
                raise RetrospectiveError("invalid_session_metadata") from None
            if not isinstance(meta, dict) or not isinstance(meta.get("payload"), dict):
                raise RetrospectiveError("invalid_session_metadata")
            if boundary is not None and not len(first) <= boundary <= stat.st_size:
                raise RetrospectiveError("invalid_source_boundary")
            if (
                meta.get("type") != "session_meta"
                or meta.get("payload", {}).get("id") != session_id
            ):
                raise RetrospectiveError("session_identity_mismatch")
            return SourceSnapshot(
                path=str(self.path),
                session_id=session_id,
                identity=self._identity(stat),
                boundary=stat.st_size if boundary is None else boundary,
                sha256=hashlib.sha256().hexdigest(),
                parser_version=PARSER_VERSION,
                settings_digest=self.settings.digest(),
            )

    def records(self, snapshot: SourceSnapshot):
        """Stream complete records within the admitted byte boundary.

        Parameters
        ----------
        snapshot : SourceSnapshot
            Committed cursor and expected identity/hash for restart.

        Yields
        ------
        SourceRecord
            Exact locator and bounded bytes; oversized payloads have no decoded data.

        Raises
        ------
        RetrospectiveError
            Source replacement, truncation or committed-prefix mutation.

        Notes
        -----
        Does not lock the writer or change the source. A partial tail is not yielded.
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
        """Rehash the committed source prefix without parsing it.

        Parameters
        ----------
        snapshot : SourceSnapshot
            Expected identity, prefix length and SHA256.

        Returns
        -------
        None
            Successful completion means the selected bytes still match.

        Raises
        ------
        RetrospectiveError
            Source replacement, truncation or prefix mutation.

        Notes
        -----
        Reads source bytes only; this does not validate statements inside them.
        """
        with open_source(self.path) as stream:
            self._check_identity(stream, snapshot)
            if (
                self._hash(stream, snapshot.indexed_bytes).hexdigest()
                != snapshot.sha256
            ):
                raise RetrospectiveError("source_prefix_changed")

    def read(self, snapshot: SourceSnapshot, locator: RecordLocator) -> bytes:
        """Retrieve one exact, bounded original record.

        Parameters
        ----------
        snapshot : SourceSnapshot
            Admitted source identity and finite prefix.
        locator : RecordLocator
            Original byte span and expected record hash.

        Returns
        -------
        bytes
            Original record bytes after span, identity and hash checks.

        Raises
        ------
        RetrospectiveError
            Oversized/out-of-range record, replacement, truncation or changed record.

        Notes
        -----
        Read-only; no extraction, execution or publication is performed.
        """
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
