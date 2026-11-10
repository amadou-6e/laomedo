"""Durable owner/generation fencing and cleanup responsibility, without secrets."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3
from uuid import UUID, uuid4

from laomedo.github.connections.errors import (
    GitHubConnectionChanged,
    GitHubConnectionError,
)
from laomedo.github.connections.models import (
    GitHubAppRecord,
    GitHubConnectionRecord,
    GitHubSecretReference,
)


class GitHubConnectionJournal:
    """Serialize custody transitions; native runtime admission precedes construction."""

    def __init__(self, path: Path):
        """Open only an explicitly admitted private database outside Git."""
        candidate = Path(path)
        if (
            not candidate.is_absolute()
            or candidate.is_symlink()
            or any((parent / ".git").exists() for parent in candidate.parents)
        ):
            raise GitHubConnectionError()
        self.path = candidate.resolve()
        if any((parent / ".git").exists() for parent in self.path.parents):
            raise GitHubConnectionError()
        try:
            with closing(self._connect()) as db, db:
                db.executescript(
                    "CREATE TABLE IF NOT EXISTS github_secrets ("
                    "id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, purpose TEXT NOT NULL, "
                    "resource_id TEXT NOT NULL, state TEXT NOT NULL CHECK "
                    "(state IN ('provisional','active','obsolete','removed')));"
                    "CREATE TABLE IF NOT EXISTS github_apps ("
                    "id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, payload TEXT NOT NULL);"
                    "CREATE TABLE IF NOT EXISTS github_connections ("
                    "id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, generation INTEGER NOT NULL, "
                    "payload TEXT NOT NULL);"
                )
        except (OSError, sqlite3.Error):
            raise GitHubConnectionError() from None

    def _connect(self):
        """Create a short-lived connection; every writer takes an immediate lock."""
        return sqlite3.connect(self.path, timeout=5)

    def _payload(self, record) -> str:
        """Persist only metadata plus its internal opaque custody reference."""
        payload = record.model_dump(mode="json")
        payload["secret_reference"] = str(record.secret_reference)
        return json.dumps(payload, separators=(",", ":"))

    def _connection(self, db, owner_id: UUID, connection_id: UUID):
        """Resolve an exact owner-scoped row and verify its redundant fence columns."""
        row = db.execute(
            "SELECT generation,payload FROM github_connections WHERE id=? AND owner_id=?",
            (str(connection_id), str(owner_id)),
        ).fetchone()
        if row is None:
            return None
        try:
            record = GitHubConnectionRecord.model_validate_json(row[1])
        except ValueError:
            raise GitHubConnectionError() from None
        if (
            record.id != connection_id
            or record.owner_id != owner_id
            or record.generation != row[0]
        ):
            raise GitHubConnectionError()
        return record

    def reserve_secret(self, owner_id: UUID, purpose: str, resource_id: UUID):
        """Journal a new provisional target before a caller can write its secret."""
        reference = GitHubSecretReference(
            id=uuid4(),
            owner_id=owner_id,
            purpose=purpose,
            resource_id=resource_id,
        )
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "INSERT INTO github_secrets VALUES (?,?,?,?, 'provisional')",
                    (str(reference.id), str(owner_id), purpose, str(resource_id)),
                )
            return reference
        except sqlite3.Error:
            raise GitHubConnectionError() from None

    def _activate(self, db, owner_id, resource_id, purpose, reference):
        """Consume only a matching provisional reservation in the current transaction."""
        changed = db.execute(
            "UPDATE github_secrets SET state='active' WHERE id=? AND owner_id=? "
            "AND resource_id=? AND purpose=? AND state='provisional'",
            (str(reference), str(owner_id), str(resource_id), purpose),
        ).rowcount
        if changed != 1:
            raise GitHubConnectionChanged()

    def save_app(self, record: GitHubAppRecord):
        """Commit a new immutable app version after its vault write was verified."""
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                self._activate(
                    db, record.owner_id, record.id, "app", record.secret_reference
                )
                db.execute(
                    "INSERT INTO github_apps VALUES (?,?,?)",
                    (str(record.id), str(record.owner_id), self._payload(record)),
                )
        except sqlite3.Error:
            raise GitHubConnectionError() from None

    def app(self, owner_id: UUID, app_id: UUID | None = None):
        """Return an exact owner-owned app version, or the latest configured version."""
        try:
            with closing(self._connect()) as db:
                if app_id is None:
                    row = db.execute(
                        "SELECT payload FROM github_apps WHERE owner_id=? ORDER BY rowid DESC LIMIT 1",
                        (str(owner_id),),
                    ).fetchone()
                else:
                    row = db.execute(
                        "SELECT payload FROM github_apps WHERE id=? AND owner_id=?",
                        (str(app_id), str(owner_id)),
                    ).fetchone()
            if row is None:
                return None
            record = GitHubAppRecord.model_validate_json(row[0])
            if record.owner_id != owner_id or (
                app_id is not None and record.id != app_id
            ):
                raise GitHubConnectionError()
            return record
        except (sqlite3.Error, ValueError):
            raise GitHubConnectionError() from None

    def commit_connection(
        self, record: GitHubConnectionRecord, *, expected_generation: int
    ):
        """Atomically replace only the selected generation after explicit read consent."""
        if (
            record.generation != expected_generation + 1
            or record.state != "ready"
            or len({repo.id for repo in record.repositories})
            != len(record.repositories)
        ):
            raise GitHubConnectionChanged()
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                current = self._connection(db, record.owner_id, record.id)
                if (
                    current.generation if current is not None else 0
                ) != expected_generation:
                    raise GitHubConnectionChanged()
                # An ID belonging to another owner must never be overwritten.
                if (
                    current is None
                    and db.execute(
                        "SELECT 1 FROM github_connections WHERE id=?", (str(record.id),)
                    ).fetchone()
                ):
                    raise GitHubConnectionChanged()
                if record.mode == "browser":
                    if (
                        record.app_id is None
                        or not db.execute(
                            "SELECT 1 FROM github_apps WHERE id=? AND owner_id=?",
                            (str(record.app_id), str(record.owner_id)),
                        ).fetchone()
                    ):
                        raise GitHubConnectionChanged()
                elif record.app_id is not None:
                    raise GitHubConnectionChanged()
                self._activate(
                    db,
                    record.owner_id,
                    record.id,
                    "connection",
                    record.secret_reference,
                )
                if current is not None:
                    db.execute(
                        "UPDATE github_secrets SET state='obsolete' WHERE id=? AND state='active'",
                        (str(current.secret_reference),),
                    )
                db.execute(
                    "INSERT INTO github_connections VALUES (?,?,?,?) ON CONFLICT(id) "
                    "DO UPDATE SET generation=excluded.generation,payload=excluded.payload",
                    (
                        str(record.id),
                        str(record.owner_id),
                        record.generation,
                        self._payload(record),
                    ),
                )
        except sqlite3.Error:
            raise GitHubConnectionError() from None

    def get(self, owner_id: UUID, connection_id: UUID):
        """Read current owner-scoped metadata without treating it as online permission."""
        try:
            with closing(self._connect()) as db:
                return self._connection(db, owner_id, connection_id)
        except sqlite3.Error:
            raise GitHubConnectionError() from None

    def list(self, owner_id: UUID):
        """List only the authenticated profile's safe connection records."""
        try:
            with closing(self._connect()) as db:
                ids = db.execute(
                    "SELECT id FROM github_connections WHERE owner_id=? ORDER BY rowid",
                    (str(owner_id),),
                ).fetchall()
                return tuple(
                    self._connection(db, owner_id, UUID(row[0])) for row in ids
                )
        except (sqlite3.Error, ValueError):
            raise GitHubConnectionError() from None

    def current(self, owner_id: UUID, connection_id: UUID, generation: int) -> bool:
        """Check the exact ready generation while the host holds its release lock."""
        record = self.get(owner_id, connection_id)
        return (
            record is not None
            and record.state == "ready"
            and record.generation == generation
        )

    def _fence(self, owner_id, connection_id, expected_generation, state):
        """Commit a monotonic admission fence before refresh or vault deletion."""
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                record = self._connection(db, owner_id, connection_id)
                if record is None or record.generation != expected_generation:
                    raise GitHubConnectionChanged()
                if state == "reauthorization_required" and record.state != "ready":
                    raise GitHubConnectionChanged()
                fenced = record.model_copy(
                    update={"generation": expected_generation + 1, "state": state}
                )
                db.execute(
                    "UPDATE github_connections SET generation=?,payload=? WHERE id=? AND owner_id=?",
                    (
                        fenced.generation,
                        self._payload(fenced),
                        str(connection_id),
                        str(owner_id),
                    ),
                )
                if state == "revoked":
                    db.execute(
                        "UPDATE github_secrets SET state='obsolete' WHERE owner_id=? "
                        "AND resource_id=? AND purpose='connection' AND state!='removed'",
                        (str(owner_id), str(connection_id)),
                    )
            return fenced
        except sqlite3.Error:
            raise GitHubConnectionError() from None

    def begin_refresh(
        self, owner_id: UUID, connection_id: UUID, expected_generation: int
    ):
        """Fence once before exchanging; restart never restores the old ready state."""
        return self._fence(
            owner_id, connection_id, expected_generation, "reauthorization_required"
        )

    def disconnect(self, owner_id: UUID, connection_id: UUID, expected_generation: int):
        """Revoke before deleting; failure to delete cannot reopen this generation."""
        return self._fence(owner_id, connection_id, expected_generation, "revoked")

    def abandon_secret(self, owner_id: UUID, reference_id: UUID):
        """Retire an uncommitted reservation without touching a ready credential."""
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "UPDATE github_secrets SET state='obsolete' WHERE id=? "
                    "AND owner_id=? AND state='provisional'",
                    (str(reference_id), str(owner_id)),
                )
        except sqlite3.Error:
            raise GitHubConnectionError() from None

    def cleanup_references(self, owner_id: UUID):
        """Return inactive journaled targets; the service must exclude live attempts."""
        try:
            with closing(self._connect()) as db:
                rows = db.execute(
                    "SELECT id,purpose,resource_id FROM github_secrets WHERE owner_id=? "
                    "AND state IN ('provisional','obsolete')",
                    (str(owner_id),),
                ).fetchall()
            return tuple(
                GitHubSecretReference(
                    id=UUID(row[0]),
                    owner_id=owner_id,
                    purpose=row[1],
                    resource_id=UUID(row[2]),
                )
                for row in rows
            )
        except (sqlite3.Error, ValueError):
            raise GitHubConnectionError() from None

    def finish_cleanup(self, owner_id: UUID, reference_id: UUID):
        """Record verified vault absence only while the target remains inactive."""
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                changed = db.execute(
                    "UPDATE github_secrets SET state='removed' WHERE id=? AND owner_id=? "
                    "AND state IN ('provisional','obsolete','removed')",
                    (str(reference_id), str(owner_id)),
                ).rowcount
                if changed != 1:
                    raise GitHubConnectionChanged()
        except sqlite3.Error:
            raise GitHubConnectionError() from None
