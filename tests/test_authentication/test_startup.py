"""Internal startup admission checks, not real account/browser acceptance."""

from contextlib import closing
from pathlib import Path
import json
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from laomedo.integrations.langflow.normal_login.startup import NormalLoginStartup


class NormalLoginStartupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="laomedo-login-startup-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "langflow").mkdir()
        (self.root / "normal-login.json").write_text(
            json.dumps({"purpose": "laomedo-normal-login", "version": 1, "port": 17866})
        )
        self.database = self.root / "langflow/flow.db"
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute(
                'CREATE TABLE "user" (username TEXT, password TEXT, is_superuser INTEGER, is_active INTEGER)'
            )
        self.context = Mock()
        self.context.verify.return_value = False
        self.auth = SimpleNamespace(
            pwd_context=self.context,
            AUTO_LOGIN=False,
            skip_auth_auto_login=False,
            ENABLE_SIGNUP=False,
            SUPERUSER="unchanged",
            SUPERUSER_PASSWORD="unchanged",
        )
        self.service = SimpleNamespace(
            auth_settings=self.auth,
            settings=SimpleNamespace(
                database_url="sqlite:///" + self.database.as_posix()
            ),
        )
        self.startup = NormalLoginStartup(self.root)

    def add_admin(self, username="chosen-admin", active=1, superuser=1):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute(
                'INSERT INTO "user" VALUES (?, ?, ?, ?)',
                (username, "internal-test-hash", superuser, active),
            )

    def test_missing_administrator_refuses_bootstrap_without_writing_marker(self):
        marker = self.startup.marker_path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "not found"):
            self.startup.confirm_bootstrap("absent", self.auth, "langflow", "legacy")
        self.assertEqual(marker, self.startup.marker_path.read_bytes())

    def test_default_name_is_refused_even_if_account_exists(self):
        self.add_admin("langflow")
        with self.assertRaisesRegex(RuntimeError, "non-default"):
            self.startup.confirm_bootstrap("langflow", self.auth, "langflow", "legacy")
        self.context.verify.assert_not_called()

    def test_inactive_or_nonadministrator_is_refused(self):
        for username, active, superuser in [("inactive", 0, 1), ("ordinary", 1, 0)]:
            with self.subTest(username=username):
                self.add_admin(username, active, superuser)
                with self.assertRaisesRegex(RuntimeError, "not found"):
                    self.startup.confirm_bootstrap(
                        username, self.auth, "langflow", "legacy"
                    )

    def test_legacy_password_is_refused_without_modifying_account(self):
        self.add_admin()
        self.context.verify.return_value = True
        with self.assertRaisesRegex(RuntimeError, "legacy default"):
            self.startup.confirm_bootstrap(
                "chosen-admin", self.auth, "langflow", "legacy"
            )
        self.context.verify.assert_called_once_with("legacy", "internal-test-hash")
        with closing(sqlite3.connect(self.database)) as db, db:
            self.assertEqual(
                db.execute('SELECT password FROM "user"').fetchone()[0],
                "internal-test-hash",
            )

    def test_validated_startup_preserves_database_and_retains_no_credential(self):
        self.add_admin()
        self.startup.confirm_bootstrap("chosen-admin", self.auth, "langflow", "legacy")
        marker = self.startup.marker_path.read_text()
        before = self.database.read_bytes()
        self.startup.prepare(self.service, "langflow", "legacy")
        self.assertEqual(self.auth.SUPERUSER, "chosen-admin")
        self.assertGreater(len(self.auth.SUPERUSER_PASSWORD.get_secret_value()), 32)
        self.assertNotIn(self.auth.SUPERUSER_PASSWORD.get_secret_value(), marker)
        self.assertNotIn("internal-test-hash", marker)
        self.assertEqual(before, self.database.read_bytes())

    def test_changed_database_or_removed_admin_refuses_before_startup(self):
        self.add_admin()
        self.startup.confirm_bootstrap("chosen-admin", self.auth, "langflow", "legacy")
        self.service.settings.database_url = "sqlite:///another.db"
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            self.startup.prepare(self.service, "langflow", "legacy")
        self.service.settings.database_url = "sqlite:///" + self.database.as_posix()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('DELETE FROM "user"')
        with self.assertRaisesRegex(RuntimeError, "not found"):
            self.startup.prepare(self.service, "langflow", "legacy")
        self.assertEqual(self.auth.SUPERUSER_PASSWORD, "unchanged")
