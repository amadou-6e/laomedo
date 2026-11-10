"""Durable ownership, crash fencing and cleanup controls; no live integration."""

from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from laomedo.github.connections.errors import (
    GitHubConnectionChanged,
    GitHubConnectionError,
)
from laomedo.github.connections.journal import GitHubConnectionJournal
from laomedo.github.connections.models import (
    GitHubAppRecord,
    GitHubConnectionRecord,
    GitHubRepositoryIdentity,
    GitHubPrincipal,
)


class GitHubConnectionJournalTests(unittest.TestCase):
    """Use real SQLite transactions and independent journal instances."""

    def setUp(self):
        """Keep synthetic metadata in a disposable directory outside the checkout."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "connections.sqlite"
        self.journal = GitHubConnectionJournal(self.path)
        self.owner, self.other, self.connection = uuid4(), uuid4(), uuid4()

    def record(self, *, generation=1, principal=123):
        """Reserve the target before simulating an already verified vault write."""
        reference = self.journal.reserve_secret(
            self.owner, "connection", self.connection
        )
        return GitHubConnectionRecord(
            id=self.connection,
            owner_id=self.owner,
            generation=generation,
            mode="token",
            principal=GitHubPrincipal(id=principal, login="synthetic-user"),
            repositories=(
                GitHubRepositoryIdentity(
                    id=456, full_name="synthetic/private", private=True
                ),
            ),
            state="ready",
            secret_reference=reference.id,
        )

    def test_restart_and_owner_filters_preserve_exact_authority(self):
        """Neither another owner nor a different generation can borrow a ready row."""
        record = self.record()
        self.journal.commit_connection(record, expected_generation=0)
        restored = GitHubConnectionJournal(self.path)
        self.assertEqual(restored.get(self.owner, self.connection), record)
        self.assertEqual(restored.list(self.other), ())
        self.assertIsNone(restored.get(self.other, self.connection))
        self.assertTrue(restored.current(self.owner, self.connection, 1))
        self.assertFalse(restored.current(self.other, self.connection, 1))
        self.assertFalse(restored.current(self.owner, self.connection, 2))
        public = record.model_dump_json()
        self.assertNotIn(str(record.secret_reference), public)

    def test_concurrent_reconnect_does_not_replace_the_winner(self):
        """A stale consent loses CAS and leaves its provisional target cleanable."""
        self.journal.commit_connection(self.record(), expected_generation=0)
        first, stale = self.record(generation=2), self.record(generation=2)
        other_instance = GitHubConnectionJournal(self.path)
        self.journal.commit_connection(first, expected_generation=1)
        with self.assertRaises(GitHubConnectionChanged):
            other_instance.commit_connection(stale, expected_generation=1)
        self.assertEqual(self.journal.get(self.owner, self.connection), first)
        cleanup = {
            reference.id for reference in self.journal.cleanup_references(self.owner)
        }
        self.assertIn(stale.secret_reference, cleanup)
        self.assertNotIn(first.secret_reference, cleanup)

    def test_refresh_crash_stays_fenced_across_restart(self):
        """A lost refresh response cannot cause replay of the consumed credential."""
        self.journal.commit_connection(self.record(), expected_generation=0)
        fenced = self.journal.begin_refresh(self.owner, self.connection, 1)
        self.assertEqual(fenced.generation, 2)
        restored = GitHubConnectionJournal(self.path)
        self.assertFalse(restored.current(self.owner, self.connection, 1))
        self.assertFalse(restored.current(self.owner, self.connection, 2))
        self.assertEqual(
            restored.get(self.owner, self.connection).state, "reauthorization_required"
        )
        with self.assertRaises(GitHubConnectionChanged):
            restored.begin_refresh(self.owner, self.connection, 2)
        replacement = self.record(generation=3)
        restored.commit_connection(replacement, expected_generation=2)
        self.assertTrue(restored.current(self.owner, self.connection, 3))

    def test_disconnect_wins_over_late_refresh_and_retains_cleanup(self):
        """Secret deletion can fail without reopening current or old admission."""
        old = self.record()
        self.journal.commit_connection(old, expected_generation=0)
        self.journal.begin_refresh(self.owner, self.connection, 1)
        replacement = self.record(generation=3)
        self.journal.disconnect(self.owner, self.connection, 2)
        with self.assertRaises(GitHubConnectionChanged):
            self.journal.commit_connection(replacement, expected_generation=2)
        restored = GitHubConnectionJournal(self.path)
        self.assertEqual(restored.get(self.owner, self.connection).state, "revoked")
        self.assertFalse(restored.current(self.owner, self.connection, 3))
        cleanup = {
            reference.id for reference in restored.cleanup_references(self.owner)
        }
        self.assertEqual(cleanup, {old.secret_reference, replacement.secret_reference})
        restored.finish_cleanup(self.owner, old.secret_reference)
        self.assertEqual(
            {reference.id for reference in restored.cleanup_references(self.owner)},
            {replacement.secret_reference},
        )

    def test_active_secret_and_other_owner_cannot_be_cleaned_or_reassigned(self):
        """A guessed reference does not authorize deleting another custody target."""
        ready = self.record()
        self.journal.commit_connection(ready, expected_generation=0)
        with self.assertRaises(GitHubConnectionChanged):
            self.journal.finish_cleanup(self.owner, ready.secret_reference)
        provisional = self.journal.reserve_secret(
            self.other, "connection", self.connection
        )
        with self.assertRaises(GitHubConnectionChanged):
            self.journal.commit_connection(
                ready.model_copy(
                    update={"owner_id": self.other, "secret_reference": provisional.id}
                ),
                expected_generation=0,
            )
        self.assertTrue(self.journal.current(self.owner, self.connection, 1))

    def test_config_versions_remain_owned_and_do_not_overwrite_ready_refresh_setup(
        self,
    ):
        """New app setup cannot silently rebind an old ready connection's app secret."""
        versions = []
        for client_id in ("Iv1.first", "Iv1.second"):
            app_id = uuid4()
            reference = self.journal.reserve_secret(self.owner, "app", app_id)
            app = GitHubAppRecord(
                id=app_id,
                owner_id=self.owner,
                client_id=client_id,
                slug="synthetic-app",
                secret_reference=reference.id,
            )
            self.journal.save_app(app)
            versions.append(app)
        self.assertEqual(self.journal.app(self.owner), versions[1])
        self.assertEqual(self.journal.app(self.owner, versions[0].id), versions[0])
        self.assertIsNone(self.journal.app(self.other, versions[0].id))
        self.assertNotIn(
            versions[0].secret_reference,
            {ref.id for ref in self.journal.cleanup_references(self.owner)},
        )

    def test_provisional_write_crash_is_discoverable_without_ready_connection(self):
        """A crash after a possible vault write retains exact cleanup responsibility."""
        reference = self.journal.reserve_secret(
            self.owner, "connection", self.connection
        )
        restored = GitHubConnectionJournal(self.path)
        self.assertEqual(restored.cleanup_references(self.owner), (reference,))
        self.assertEqual(restored.list(self.owner), ())
        restored.abandon_secret(self.owner, reference.id)
        restored.finish_cleanup(self.owner, reference.id)
        restored.finish_cleanup(self.owner, reference.id)
        self.assertEqual(restored.cleanup_references(self.owner), ())

    def test_in_checkout_database_is_refused_before_creation(self):
        """A credential journal cannot accidentally be created inside a Git tree."""
        root = Path(self.directory.name) / "repo"
        root.mkdir()
        (root / ".git").write_text("gitdir: synthetic", encoding="utf-8")
        with self.assertRaises(GitHubConnectionError):
            GitHubConnectionJournal(root / "connections.sqlite")
        self.assertFalse((root / "connections.sqlite").exists())
