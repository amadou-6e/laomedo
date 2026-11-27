"""Durable, owner-bound revocable leases for private browser reads."""

from contextlib import closing
from hashlib import sha256
from pathlib import Path
import secrets
import sqlite3
import time
from typing import Callable
from uuid import UUID

from pydantic import SecretStr

from laomedo.integrations.langflow.authentication.errors import PrivateSessionError
from laomedo.integrations.langflow.authentication.models import (
    IssuedPrivateSession,
    PrivateSession,
)


class PrivateSessionStore:
    """Persist cookie digests; serialize renewal and revocation across instances."""

    def __init__(self, path: Path, *, now: Callable[[], float] = time.time):
        candidate = Path(path)
        if (
            not candidate.is_absolute()
            or candidate.is_symlink()
            or any((parent / ".git").exists() for parent in candidate.parents)
        ):
            raise PrivateSessionError()
        self.path = candidate.resolve()
        if any((parent / ".git").exists() for parent in self.path.parents):
            raise PrivateSessionError()
        self.now = now
        try:
            with closing(self._connect()) as db, db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS private_sessions ("
                    "digest TEXT PRIMARY KEY, owner_id TEXT NOT NULL, "
                    "issued_at REAL NOT NULL, expires_at REAL NOT NULL, "
                    "revoked INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0,1)))"
                )
        except (OSError, sqlite3.Error):
            raise PrivateSessionError() from None

    def _connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def _digest(self, cookie: SecretStr) -> str:
        return sha256(cookie.get_secret_value().encode("utf-8")).hexdigest()

    def issue(self, owner_id: UUID, *, expires_at: float) -> IssuedPrivateSession:
        """Mint only after a verified upstream login; refuse an elapsed lifetime."""
        issued_at = float(self.now())
        session = PrivateSession(
            owner_id=owner_id, issued_at=issued_at, expires_at=expires_at
        )
        if session.expires_at <= issued_at:
            raise PrivateSessionError()
        cookie = SecretStr(secrets.token_urlsafe(32))
        try:
            with closing(self._connect()) as db, db:
                db.execute(
                    "INSERT INTO private_sessions "
                    "(digest, owner_id, issued_at, expires_at) VALUES (?,?,?,?)",
                    (
                        self._digest(cookie),
                        str(session.owner_id),
                        session.issued_at,
                        session.expires_at,
                    ),
                )
        except (OSError, sqlite3.Error):
            raise PrivateSessionError() from None
        return IssuedPrivateSession(session=session, cookie=cookie)

    def resolve(self, cookie: SecretStr, owner_id: UUID) -> PrivateSession | None:
        """Read only a live lease bound to the already-authenticated owner."""
        try:
            with closing(self._connect()) as db:
                row = db.execute(
                    "SELECT issued_at, expires_at FROM private_sessions "
                    "WHERE digest=? AND owner_id=? AND revoked=0 AND expires_at>?",
                    (self._digest(cookie), str(owner_id), self.now()),
                ).fetchone()
        except (OSError, sqlite3.Error):
            raise PrivateSessionError() from None
        if row is None:
            return None
        return PrivateSession(owner_id=owner_id, issued_at=row[0], expires_at=row[1])

    def renew(self, cookie: SecretStr, owner_id: UUID, *, expires_at: float) -> bool:
        """Extend a live matching lease, never shortening or resurrecting it."""
        try:
            with closing(self._connect()) as db, db:
                # Evaluate expiry after acquiring the write lock: time spent
                # waiting for another transaction must not revive an old lease.
                db.execute("BEGIN IMMEDIATE")
                now = float(self.now())
                lifetime = PrivateSession(
                    owner_id=owner_id, issued_at=now, expires_at=expires_at
                )
                if lifetime.expires_at <= now:
                    return False
                result = db.execute(
                    "UPDATE private_sessions SET expires_at=MAX(expires_at, ?) "
                    "WHERE digest=? AND owner_id=? AND revoked=0 AND expires_at>?",
                    (lifetime.expires_at, self._digest(cookie), str(owner_id), now),
                )
                return result.rowcount == 1
        except (OSError, sqlite3.Error):
            raise PrivateSessionError() from None

    def revoke(self, cookie: SecretStr, owner_id: UUID) -> None:
        """Commit a fence for this browser only, including an expired lease."""
        try:
            with closing(self._connect()) as db, db:
                db.execute(
                    "UPDATE private_sessions SET revoked=1 WHERE digest=? AND owner_id=?",
                    (self._digest(cookie), str(owner_id)),
                )
        except (OSError, sqlite3.Error):
            raise PrivateSessionError() from None

    def revoke_browser(self, cookie: SecretStr) -> None:
        """Fence only the presented browser capability, even after JWT expiry."""
        try:
            with closing(self._connect()) as db, db:
                db.execute(
                    "UPDATE private_sessions SET revoked=1 WHERE digest=?",
                    (self._digest(cookie),),
                )
        except (OSError, sqlite3.Error):
            raise PrivateSessionError() from None

    def is_revoked(self, cookie: SecretStr) -> bool:
        """Recognize a durable logout fence; an unknown value grants nothing."""
        try:
            with closing(self._connect()) as db:
                row = db.execute(
                    "SELECT revoked FROM private_sessions WHERE digest=?",
                    (self._digest(cookie),),
                ).fetchone()
        except (OSError, sqlite3.Error):
            raise PrivateSessionError() from None
        return row is not None and bool(row[0])
