"""Synthetic #108 broker boundary; not production credential storage."""

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sqlite3
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit


class ConnectionRefused(Exception):
    pass


class ConnectionBroker:
    def __init__(self, database, provider_url):
        parsed = urlsplit(provider_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ConnectionRefused("synthetic_provider_must_be_loopback")
        self.database = Path(database)
        self.provider_url = provider_url.rstrip("/")
        with closing(self._db()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS pending (
                    state TEXT PRIMARY KEY, owner TEXT NOT NULL,
                    session TEXT NOT NULL, account TEXT NOT NULL,
                    repository TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS connections (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, mode TEXT NOT NULL,
                    account TEXT NOT NULL, repository TEXT NOT NULL,
                    generation INTEGER NOT NULL, state TEXT NOT NULL,
                    secret TEXT, expires_at TEXT
                );
                CREATE TABLE IF NOT EXISTS grants (
                    capability TEXT PRIMARY KEY, connection_id TEXT NOT NULL,
                    generation INTEGER NOT NULL, owner TEXT NOT NULL,
                    repository TEXT NOT NULL, operations TEXT NOT NULL
                );
            """)

    def _db(self):
        db = sqlite3.connect(self.database)
        db.row_factory = sqlite3.Row
        return db

    def _provider(self, endpoint, payload):
        request = Request(self.provider_url + endpoint,
                          data=json.dumps(payload).encode("utf-8"),
                          headers={"Content-Type": "application/json"},
                          method="POST")
        try:
            with urlopen(request, timeout=3) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise ConnectionRefused("provider_unavailable_or_rejected") from exc

    def begin_browser(self, *, owner, session, account, repository):
        if not all((owner, session, account, repository)):
            raise ConnectionRefused("missing_browser_binding")
        state = secrets.token_urlsafe(24)
        with closing(self._db()) as db, db:
            db.execute("INSERT INTO pending VALUES (?, ?, ?, ?, ?)",
                       (state, owner, session, account, repository))
        return {"state": state, "mode": "browser", "provider": self.provider_url}

    def finish_browser(self, *, owner, session, state, code):
        with closing(self._db()) as db, db:
            pending = db.execute("SELECT * FROM pending WHERE state=?", (state,)).fetchone()
            if pending is None or pending["owner"] != owner or pending["session"] != session:
                raise ConnectionRefused("callback_binding_mismatch")
            # The exchange is deliberately inside the transaction so a replay
            # cannot consume the same challenge twice.
            db.execute("BEGIN IMMEDIATE")
            pending = db.execute("SELECT * FROM pending WHERE state=?", (state,)).fetchone()
            if pending is None:
                raise ConnectionRefused("callback_replayed")
            exchanged = self._provider("/exchange", {"code": code, "state": state})
            token = exchanged.get("token")
            verified = self._verify(token, pending["account"], pending["repository"],
                                    ("contents:write",), "app_user")
            connection_id = secrets.token_urlsafe(18)
            db.execute("INSERT INTO connections VALUES (?, ?, 'browser', ?, ?, 1, 'ready', ?, ?)",
                       (connection_id, owner, verified["account"],
                        pending["repository"], token, verified["expires_at"]))
            db.execute("DELETE FROM pending WHERE state=?", (state,))
        return self.describe(connection_id, owner)

    def connect_token(self, *, owner, account, repository, token):
        verified = self._verify(token, account, repository,
                                ("contents:write",), "fine_grained")
        connection_id = secrets.token_urlsafe(18)
        with closing(self._db()) as db, db:
            db.execute("INSERT INTO connections VALUES (?, ?, 'token', ?, ?, 1, 'ready', ?, ?)",
                       (connection_id, owner, verified["account"], repository,
                        token, verified["expires_at"]))
        return self.describe(connection_id, owner)

    def replace_token(self, *, connection_id, owner, token):
        with closing(self._db()) as db, db:
            row = self._owned(db, connection_id, owner)
            if row["mode"] != "token":
                raise ConnectionRefused("wrong_connection_mode")
            verified = self._verify(token, row["account"], row["repository"],
                                    ("contents:write",), "fine_grained")
            db.execute("UPDATE connections SET generation=generation+1, secret=?, expires_at=?, state='ready' WHERE id=?",
                       (token, verified["expires_at"], connection_id))
        return self.describe(connection_id, owner)

    def _verify(self, token, account, repository, operations, token_type):
        if not token or not isinstance(token, str):
            raise ConnectionRefused("missing_explicit_credential")
        result = self._provider("/verify", {"token": token})
        if (result.get("type") != token_type or result.get("account") != account or
                repository not in result.get("repositories", []) or
                not set(operations).issubset(result.get("operations", []))):
            raise ConnectionRefused("identity_or_scope_mismatch")
        expiry = result.get("expires_at")
        if not expiry or datetime.fromisoformat(expiry) <= datetime.now(timezone.utc):
            raise ConnectionRefused("credential_expired")
        return result

    def _owned(self, db, connection_id, owner):
        row = db.execute("SELECT * FROM connections WHERE id=? AND owner=?",
                         (connection_id, owner)).fetchone()
        if row is None:
            raise ConnectionRefused("connection_not_owned")
        return row

    def describe(self, connection_id, owner):
        with closing(self._db()) as db:
            row = self._owned(db, connection_id, owner)
            return {key: row[key] for key in
                    ("id", "owner", "mode", "account", "repository", "generation", "state", "expires_at")}

    def issue_run(self, *, connection_id, owner, repository, operations):
        with closing(self._db()) as db, db:
            row = self._owned(db, connection_id, owner)
            if row["state"] != "ready" or row["repository"] != repository:
                raise ConnectionRefused("connection_unavailable")
            self._verify(row["secret"], row["account"], repository,
                         operations, "app_user" if row["mode"] == "browser" else "fine_grained")
            capability = secrets.token_urlsafe(24)
            db.execute("INSERT INTO grants VALUES (?, ?, ?, ?, ?, ?)",
                       (capability, connection_id, row["generation"], owner,
                        repository, json.dumps(operations)))
        return {"capability": capability, "repository": repository,
                "operations": list(operations)}

    def mediated_write(self, capability, operation):
        with closing(self._db()) as db:
            row = db.execute("""SELECT g.generation AS grant_generation, g.operations,
                     g.repository AS grant_repository, c.* FROM grants g
                     JOIN connections c ON c.id=g.connection_id
                     WHERE g.capability=?""", (capability,)).fetchone()
            if (row is None or row["state"] != "ready" or
                    row["grant_generation"] != row["generation"] or
                    operation not in json.loads(row["operations"])):
                raise ConnectionRefused("run_grant_revoked_or_invalid")
            self._verify(row["secret"], row["account"], row["grant_repository"],
                         (operation,), "app_user" if row["mode"] == "browser" else "fine_grained")
            return self._provider("/write", {"token": row["secret"],
                                             "repository": row["grant_repository"],
                                             "operation": operation})

    def disconnect(self, connection_id, owner):
        with closing(self._db()) as db, db:
            self._owned(db, connection_id, owner)
            db.execute("UPDATE connections SET generation=generation+1, state='revoked', secret=NULL WHERE id=?",
                       (connection_id,))
