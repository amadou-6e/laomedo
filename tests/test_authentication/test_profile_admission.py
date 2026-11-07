"""Internal fail-closed admission checks; no browser acceptance claim."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from laomedo.integrations.langflow.local_profiles.admission import (
    ProfileRuntimeAdmission,
)
from laomedo.integrations.langflow.local_profiles.errors import ProfileError


class ProfileAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "langflow").mkdir()
        (self.root / "local-profiles.json").write_text(
            json.dumps(
                {"purpose": "laomedo-local-profiles", "version": 1, "port": 17866}
            )
        )
        self.admission = ProfileRuntimeAdmission(self.root)
        self.auth = SimpleNamespace(
            AUTO_LOGIN=False,
            skip_auth_auto_login=False,
            ENABLE_SIGNUP=False,
            NEW_USER_IS_ACTIVE=True,
            EXTERNAL_AUTH_ENABLED=False,
            API_KEY_SOURCE="db",
            pwd_context=Mock(),
        )
        self.service = SimpleNamespace(
            auth_settings=self.auth,
            settings=SimpleNamespace(
                database_url="sqlite:///" + self.admission.database.as_posix()
            ),
        )

    def test_absent_or_empty_owned_database_is_fresh(self):
        self.assertTrue(self.admission.verify_database(self.auth))
        self.admission.database.touch()
        self.assertTrue(self.admission.verify_database(self.auth))

    def test_unrelated_tables_and_partial_schema_are_not_fresh(self):
        for query in (
            "CREATE TABLE other (id TEXT)",
            'CREATE TABLE "user" (id TEXT, username TEXT)',
        ):
            with self.subTest(query=query):
                self.admission.database.unlink(missing_ok=True)
                with closing(sqlite3.connect(self.admission.database)) as db:
                    db.execute(query)
                    db.commit()
                before = self.admission.database.read_bytes()
                with self.assertRaises(ProfileError):
                    self.admission.verify_database(self.auth)
                self.assertEqual(self.admission.database.read_bytes(), before)

    def test_corruption_is_refused_without_repair(self):
        self.admission.database.write_bytes(b"not a sqlite database")
        with self.assertRaises(ProfileError):
            self.admission.verify_database(self.auth)
        self.assertEqual(self.admission.database.read_bytes(), b"not a sqlite database")

    def test_effective_auth_bypasses_are_refused(self):
        for name, value in (
            ("AUTO_LOGIN", True),
            ("skip_auth_auto_login", True),
            ("ENABLE_SIGNUP", True),
            ("NEW_USER_IS_ACTIVE", False),
            ("EXTERNAL_AUTH_ENABLED", True),
            ("API_KEY_SOURCE", "env"),
        ):
            with (
                self.subTest(name=name),
                patch.object(self.auth, name, value),
                self.assertRaises(ProfileError),
            ):
                self.admission.verify_settings(self.service)
        with (
            patch.dict("os.environ", {"LANGFLOW_API_KEY": "not-a-real-key"}),
            self.assertRaises(ProfileError),
        ):
            self.admission.verify_settings(self.service)

    def test_startup_value_is_only_set_in_process_after_admission(self):
        with patch.dict("os.environ", {}, clear=True):
            self.admission.prepare(self.service)
            self.assertNotEqual(self.auth.SUPERUSER_PASSWORD.get_secret_value(), "")
            import os

            self.assertNotIn("LANGFLOW_SUPERUSER_PASSWORD", os.environ)
        self.assertFalse(self.admission.database.exists())

    def test_missing_marker_is_not_authorization_to_initialize(self):
        (self.root / "local-profiles.json").unlink()
        with self.assertRaises(ProfileError):
            ProfileRuntimeAdmission(self.root)
