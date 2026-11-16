"""Synthetic credential-boundary checks; these are not real login acceptance."""

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from laomedo.host.credentials.siwc.settings import NEEDED
from laomedo.host.provider_connections.errors import ProviderConnectionError
from laomedo.host.provider_connections.service import ProviderConnections


class ProviderConnectionsTests(unittest.TestCase):
    """Exercise exact-owner routing, staged replacement and callback fencing."""

    def setUp(self):
        """Give each case a private disposable store and unrelated local profiles."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "providers"
        self.service = ProviderConnections(self.root)
        self.addCleanup(self.service.close)
        self.profile = uuid4()
        self.other_profile = uuid4()

    def connect(
        self, subject="one", client="oaiapp_one", connection_id=None, exchange=None
    ):
        """Complete an explicit synthetic authorization without invoking a model."""
        receipt, _url = self.service.begin(
            self.profile, "http://127.0.0.1:17867/auth/callback", connection_id
        )
        pending = self.service._attempts[receipt.attempt_id]
        oauth = json.loads(pending.oauth.get_secret_value())
        result = self.service.complete(
            self.profile,
            {"state": oauth["state"], "code": "fixture", "client_id": client},
            exchange=exchange
            or (
                lambda *args, **kwargs: {
                    "access_token": subject + "-access",
                    "refresh_token": subject + "-refresh",
                    "id_token": "fixture-id",
                    "scope": " ".join(NEEDED),
                    "expires_in": 3600,
                }
            ),
            verify=lambda *args: {
                "iss": "https://auth.openai.com",
                "sub": subject,
                "email": subject + "@example.invalid",
            },
        )
        return result

    def test_two_accounts_remain_independently_selectable_after_restart(self):
        """Every lookup requires this profile and exact connection/generation."""
        one = self.connect()
        two = self.connect("two", "oaiapp_two")
        self.service.close()
        restarted = ProviderConnections(self.root)
        self.addCleanup(restarted.close)
        self.assertEqual(
            restarted.borrow(self.profile, one.connection_id, 1)[0], "one-access"
        )
        self.assertEqual(
            restarted.borrow(self.profile, two.connection_id, 1)[0], "two-access"
        )
        self.assertEqual(restarted.list(self.other_profile), [])
        with self.assertRaisesRegex(
            ProviderConnectionError, "provider_connection_unavailable"
        ):
            restarted.borrow(self.other_profile, one.connection_id, 1)
        public = json.dumps(
            [item.model_dump(mode="json") for item in restarted.list(self.profile)]
        )
        for private in (
            "one-access",
            "one-refresh",
            "client_id",
            "credential_id",
            "credential_ref",
        ):
            self.assertNotIn(private, public)

    def test_duplicate_offers_existing_without_overwrite(self):
        """Verified issuer/subject duplicates reuse the existing saved identity."""
        existing = self.connect()
        duplicate = self.connect("one", "oaiapp_another")
        self.assertEqual(duplicate.status, "duplicate")
        self.assertEqual(duplicate.connection_id, existing.connection_id)
        self.assertEqual(len(self.service.list(self.profile)), 1)
        self.assertEqual(
            self.service.borrow(self.profile, existing.connection_id, 1)[0],
            "one-access",
        )

    def test_wrong_account_reconnect_preserves_committed_credential(self):
        """A native return for another principal cannot replace a working login."""
        existing = self.connect()
        failure = self.connect("wrong", "oaiapp_one", existing.connection_id)
        self.assertEqual(failure.status, "failed")
        self.assertEqual(
            self.service.borrow(self.profile, existing.connection_id, 1)[0],
            "one-access",
        )

    def test_cancel_during_exchange_fences_late_result_and_scrubs_staging(self):
        """Cancellation remains available while network verification is blocked."""
        entered, release = threading.Event(), threading.Event()
        receipt, _url = self.service.begin(
            self.profile, "http://127.0.0.1:17867/auth/callback"
        )
        pending = self.service._attempts[receipt.attempt_id]
        oauth = json.loads(pending.oauth.get_secret_value())
        outcomes = []

        def exchange(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(5))
            return {
                "access_token": "late-access",
                "refresh_token": "late-refresh",
                "id_token": "id",
                "scope": " ".join(NEEDED),
                "expires_in": 3600,
            }

        worker = threading.Thread(
            target=lambda: outcomes.append(
                self.service.complete(
                    self.profile,
                    {
                        "state": oauth["state"],
                        "code": "code",
                        "client_id": "oaiapp_late",
                    },
                    exchange=exchange,
                    verify=lambda *args: {
                        "iss": "https://auth.openai.com",
                        "sub": "late",
                    },
                )
            )
        )
        worker.start()
        try:
            self.assertTrue(entered.wait(5))
            self.assertEqual(
                self.service.cancel(self.profile, receipt.attempt_id).status,
                "cancelled",
            )
        finally:
            release.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(outcomes[0].status, "cancelled")
        self.assertEqual(self.service.list(self.profile), [])
        self.assertEqual(list((pending.stage / "accounts").glob("*.json")), [])

    def test_logout_and_expiry_refuse_callback_replay(self):
        """Neither polling nor a restart can resume invalidated authorizations."""
        receipt, _url = self.service.begin(
            self.profile, "http://127.0.0.1:17867/auth/callback"
        )
        pending = self.service._attempts[receipt.attempt_id]
        state = json.loads(pending.oauth.get_secret_value())["state"]
        self.service.cancel_profile(self.profile)
        with self.assertRaisesRegex(ProviderConnectionError, "provider_login_expired"):
            self.service.complete(self.profile, {"state": state})
        self.service.close()
        restarted = ProviderConnections(self.root)
        self.addCleanup(restarted.close)
        with self.assertRaisesRegex(ProviderConnectionError, "provider_login_expired"):
            restarted.progress(self.profile, receipt.attempt_id)

    def test_failed_metadata_commit_does_not_replace_old_credential(self):
        """The metadata pointer is the only admission point for staged credentials."""
        existing = self.connect()
        from laomedo.host.provider_connections.service import _atomic_private

        def fail_metadata(path, value):
            if path.name == "connections.json":
                raise OSError("fixture write failed")
            return _atomic_private(path, value)

        with patch(
            "laomedo.host.provider_connections.service._atomic_private",
            side_effect=fail_metadata,
        ):
            result = self.connect(connection_id=existing.connection_id)
            self.assertEqual(result.status, "failed")
        self.assertEqual(
            self.service.borrow(self.profile, existing.connection_id, 1)[0],
            "one-access",
        )

    def test_reconnect_advances_identity_epoch_and_scrubs_previous_vault(self):
        """Reconnect validates before replacing the pointer and erases the old copy."""
        existing = self.connect()
        previous = self.service._record(self.profile, existing.connection_id)
        broker = self.service._broker(self.profile, previous.credential_id)
        result = self.connect(connection_id=existing.connection_id)
        self.assertEqual(result.status, "connected")
        self.assertEqual(self.service.list(self.profile)[0].generation, 2)
        self.assertFalse(broker._path(previous.client_id).exists())
        with self.assertRaisesRegex(
            ProviderConnectionError, "provider_connection_changed"
        ):
            self.service.borrow(self.profile, existing.connection_id, 1)

    def test_post_commit_error_reconciles_saved_state_before_reporting_failure(self):
        """A completed atomic rename is confirmed by readback, never repeated."""
        from laomedo.host.provider_connections.service import _atomic_private

        existing = self.connect()

        def uncertain(path, value):
            _atomic_private(path, value)
            if path.name == "connections.json":
                raise OSError("fixture error after publication")

        with patch(
            "laomedo.host.provider_connections.service._atomic_private",
            side_effect=uncertain,
        ):
            result = self.connect(connection_id=existing.connection_id)
        self.assertEqual(result.status, "connected")
        self.assertEqual(
            self.service.borrow(self.profile, existing.connection_id, 2)[0],
            "one-access",
        )
        files = list((self.root / str(self.profile)).glob("*/accounts/*.json"))
        self.assertEqual(len(files), 1)

    def test_slow_token_rotation_does_not_block_cancelling_another_attempt(self):
        """Provider transport waits never hold the global lifecycle fence."""
        from laomedo.host.credentials.siwc.connection import ChatGPTConnection

        existing = self.connect()
        receipt, _url = self.service.begin(
            self.profile, "http://127.0.0.1:17867/auth/callback"
        )
        entered, release, cancelled = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )
        original = ChatGPTConnection.access_token

        def slow(selected, client_id):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("fixture release missing")
            return original(selected, client_id)

        def cancel():
            self.service.cancel(self.profile, receipt.attempt_id)
            cancelled.set()

        with patch.object(
            ChatGPTConnection, "access_token", autospec=True, side_effect=slow
        ):
            worker = threading.Thread(
                target=lambda: self.service.borrow(
                    self.profile, existing.connection_id, 1
                )
            )
            worker.start()
            try:
                self.assertTrue(entered.wait(5))
                cancellation = threading.Thread(target=cancel)
                cancellation.start()
                self.assertTrue(cancelled.wait(1))
            finally:
                release.set()
                worker.join(5)
                cancellation.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(
            self.service.progress(self.profile, receipt.attempt_id).status, "cancelled"
        )

    def test_terminal_cancel_does_not_wait_for_credential_cleanup(self):
        """Cancelling an observed completion never acquires a credential lock."""
        existing = self.connect()
        receipt = self.connect(connection_id=existing.connection_id)
        pending = self.service._attempts[receipt.attempt_id]
        pending.superseded_scrubbed = False
        with patch.object(
            self.service,
            "_scrub",
            side_effect=AssertionError("cancellation must not wait for token cleanup"),
        ):
            result = self.service.cancel(self.profile, receipt.attempt_id)
        self.assertEqual(result.status, "connected")
        self.assertEqual(result.connection_id, existing.connection_id)

    def test_rotation_keeps_the_saved_identity_epoch_without_index_write(self):
        """Routine rotation cannot invalidate a selected connection generation."""
        from laomedo.host.credentials.siwc.connection import ChatGPTConnection
        from laomedo.host.credentials.siwc.utils import _atomic_private

        existing = self.connect()
        record = self.service._record(self.profile, existing.connection_id)
        broker = self.service._broker(self.profile, record.credential_id)
        account = broker.account(record.client_id)
        account["expires_at"] = 0
        _atomic_private(broker._path(record.client_id), account)
        original = ChatGPTConnection.access_token

        def rotate(selected, client_id):
            return original(
                selected,
                client_id,
                refresh=lambda *args, **kwargs: {
                    "access_token": "rotated-access",
                    "refresh_token": "rotated-refresh",
                    "expires_in": 3600,
                },
            )

        with (
            patch.object(
                ChatGPTConnection, "access_token", autospec=True, side_effect=rotate
            ),
            patch.object(
                self.service,
                "_save",
                side_effect=AssertionError("rotation must not rewrite identity"),
            ),
        ):
            token, identity = self.service.borrow(
                self.profile, existing.connection_id, 1
            )
        self.assertEqual(token, "rotated-access")
        self.assertEqual(identity["connection_generation"], 1)
        self.assertEqual(identity["credential_generation"], 2)
        self.assertEqual(self.service.list(self.profile)[0].auth_state, "ready")
        self.assertEqual(broker.account(record.client_id)["generation"], 2)
        self.assertEqual(
            self.service.borrow(self.profile, existing.connection_id, 1)[0],
            "rotated-access",
        )

    def test_restart_scrubs_crash_left_staging_without_touching_saved_account(self):
        """Startup reconciles only owner-known vaults absent from the index."""
        from laomedo.host.credentials.siwc.connection import ChatGPTConnection
        from laomedo.host.credentials.siwc.utils import _atomic_private

        existing = self.connect()
        record = self.service._record(self.profile, existing.connection_id)
        original = self.service._broker(self.profile, record.credential_id)
        orphan = ChatGPTConnection(
            self.root / str(self.profile) / ("pending-" + str(uuid4()))
        )
        _atomic_private(
            orphan._path(record.client_id), original.account(record.client_id)
        )
        partial = original._path(record.client_id).with_name(
            original._path(record.client_id).name + ".pending-" + uuid4().hex
        )
        partial.write_text("partial-private-token", encoding="utf-8")
        self.service.close()
        restarted = ProviderConnections(self.root)
        self.addCleanup(restarted.close)
        self.assertFalse(orphan._path(record.client_id).exists())
        self.assertFalse(partial.exists())
        self.assertEqual(
            restarted.borrow(self.profile, existing.connection_id, 1)[0], "one-access"
        )

    def test_corrupt_index_is_not_presented_as_empty(self):
        """Unavailable saved state must not imply a user lost every connection."""
        self.connect()
        (self.root / str(self.profile) / "connections.json").write_text(
            "invalid", encoding="utf-8"
        )
        with self.assertRaisesRegex(
            ProviderConnectionError, "provider_connections_unavailable"
        ):
            self.service.list(self.profile)
