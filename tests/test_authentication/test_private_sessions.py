"""Internal durable lease controls; these do not establish browser acceptance."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from uuid import uuid4

from pydantic import SecretStr

from laomedo.integrations.langflow.authentication.errors import PrivateSessionError
from laomedo.integrations.langflow.authentication.store import PrivateSessionStore


class LeaseRace:
    def __init__(self, path, cookie, owner):
        self.store = PrivateSessionStore(path, now=lambda: 100.0)
        self.cookie = cookie
        self.owner = owner
        self.barrier = threading.Barrier(2, timeout=5)

    def renew(self):
        self.barrier.wait()
        return self.store.renew(self.cookie, self.owner, expires_at=300.0)

    def revoke(self):
        self.barrier.wait()
        self.store.revoke(self.cookie, self.owner)


class PrivateSessionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "sessions.sqlite"
        self.now = 100.0
        self.owner = uuid4()
        self.store = PrivateSessionStore(self.path, now=lambda: self.now)

    def test_restart_preserves_live_lease_and_cookie_is_not_persisted(self):
        issued = self.store.issue(self.owner, expires_at=200.0)
        reopened = PrivateSessionStore(self.path, now=lambda: self.now)
        self.assertEqual(reopened.resolve(issued.cookie, self.owner), issued.session)
        self.assertNotIn(issued.cookie.get_secret_value(), repr(issued))
        self.assertNotIn("cookie", issued.model_dump())
        with closing(sqlite3.connect(self.path)) as db:
            self.assertNotIn(
                issued.cookie.get_secret_value(),
                str(db.execute("SELECT * FROM private_sessions").fetchall()),
            )

    def test_wrong_owner_and_unknown_cookie_never_resolve_or_renew(self):
        issued = self.store.issue(self.owner, expires_at=200.0)
        other = uuid4()
        self.assertIsNone(self.store.resolve(issued.cookie, other))
        self.assertFalse(self.store.renew(issued.cookie, other, expires_at=300.0))
        self.store.revoke(issued.cookie, other)
        self.assertIsNotNone(self.store.resolve(issued.cookie, self.owner))
        self.assertIsNone(self.store.resolve(SecretStr("unknown"), self.owner))
        self.assertFalse(
            self.store.renew(SecretStr("unknown"), self.owner, expires_at=300.0)
        )

    def test_expired_lease_cannot_be_renewed(self):
        issued = self.store.issue(self.owner, expires_at=200.0)
        self.now = 200.0
        self.assertIsNone(self.store.resolve(issued.cookie, self.owner))
        self.assertFalse(self.store.renew(issued.cookie, self.owner, expires_at=300.0))

    def test_refresh_extends_existing_live_lease_and_logout_is_independent(self):
        first = self.store.issue(self.owner, expires_at=200.0)
        second = self.store.issue(self.owner, expires_at=200.0)
        self.assertNotEqual(first.cookie, second.cookie)
        self.assertTrue(self.store.renew(first.cookie, self.owner, expires_at=300.0))
        self.store.revoke(first.cookie, self.owner)
        restarted = PrivateSessionStore(self.path, now=lambda: self.now)
        self.assertIsNone(restarted.resolve(first.cookie, self.owner))
        self.assertFalse(restarted.renew(first.cookie, self.owner, expires_at=400.0))
        self.assertIsNotNone(restarted.resolve(second.cookie, self.owner))

    def test_concurrent_refresh_cannot_overwrite_logout(self):
        issued = self.store.issue(self.owner, expires_at=200.0)
        race = LeaseRace(self.path, issued.cookie, self.owner)
        with ThreadPoolExecutor(max_workers=2) as pool:
            refresh = pool.submit(race.renew)
            logout = pool.submit(race.revoke)
            refresh.result(timeout=10)
            logout.result(timeout=10)
        self.assertIsNone(self.store.resolve(issued.cookie, self.owner))
        self.assertFalse(self.store.renew(issued.cookie, self.owner, expires_at=400.0))

    def test_elapsed_issuance_and_database_failure_stay_locked(self):
        with self.assertRaises(PrivateSessionError):
            self.store.issue(self.owner, expires_at=100.0)
        self.path.unlink()
        with self.assertRaises(PrivateSessionError) as error:
            self.store.resolve(SecretStr("not-a-real-cookie"), self.owner)
        self.assertEqual(error.exception.args, ("private_session_unavailable",))

    def test_relative_and_git_owned_database_paths_are_refused(self):
        with self.assertRaises(PrivateSessionError):
            PrivateSessionStore(Path("relative.sqlite"))
        (Path(self.temp.name) / ".git").mkdir()
        with self.assertRaises(PrivateSessionError):
            PrivateSessionStore(self.path)
