"""Synthetic credential-boundary checks; these are not real login acceptance."""

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from laomedo.host.credentials.siwc.settings import NEEDED
from laomedo.host.credentials.siwc.errors import AuthError
from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.connections.service import ProviderConnections
from laomedo.agents.connections.models import GraphProviderPreferences


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
        self,
        subject="one",
        client="oaiapp_one",
        connection_id=None,
        exchange=None,
        email=None,
    ):
        """Complete an explicit synthetic authorization without invoking a model."""
        receipt, _url = self.service.begin(
            self.profile, "http://127.0.0.1:17867/auth/callback", connection_id
        )
        pending = self.service.codex.attempts[receipt.attempt_id]
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
                "email": email or subject + "@example.invalid",
            },
        )
        return result

    def test_callback_diagnostics_never_log_raw_provider_failure_data(self):
        """Known categories aid diagnosis; arbitrary exception content stays private."""
        for category in (
            "auth_http_401",
            "auth_account_mismatch",
            "private-token-fixture",
        ):
            with (
                self.subTest(category=category),
                self.assertLogs(
                    "laomedo.agents.agents.codex.connection", level="WARNING"
                ) as captured,
            ):
                result = self.connect(exchange=Mock(side_effect=AuthError(category)))
            self.assertEqual(result.status, "failed")
            message = " ".join(captured.output)
            self.assertIn("phase=exchange_and_verification", message)
            self.assertNotIn("private-token-fixture", message)
            self.assertIn(
                "category="
                + (category if category.startswith("auth_") else "unclassified"),
                message,
            )

    def test_graph_preference_is_owned_persistent_and_independent(self):
        """A preference selects only this profile and graph, without changing credentials."""
        connection = self.connect().connection_id
        graph, other_graph = uuid4(), uuid4()
        preference = GraphProviderPreferences(codex=connection)
        self.service.save_graph_preferences(self.profile, graph, preference)
        self.assertEqual(
            self.service.graph_preferences(self.profile, graph).codex, connection
        )
        self.assertIsNone(
            self.service.graph_preferences(self.profile, other_graph).codex
        )
        self.assertIsNone(
            self.service.graph_preferences(self.other_profile, graph).codex
        )
        with self.assertRaises(ProviderConnectionError):
            self.service.save_graph_preferences(self.other_profile, graph, preference)
        self.service.close()
        self.service = ProviderConnections(self.root)
        self.addCleanup(self.service.close)
        self.assertEqual(
            self.service.graph_preferences(self.profile, graph).codex, connection
        )
        self.service.save_graph_preferences(
            self.profile, graph, GraphProviderPreferences()
        )
        self.assertIsNone(self.service.graph_preferences(self.profile, graph).codex)
        self.assertEqual(len(self.service.list(self.profile)), 1)

    def test_graph_preferences_reject_cross_provider_and_foreign_bindings(self):
        """One harness cannot borrow another harness's or profile's connection."""
        codex = self.connect().connection_id
        graph = uuid4()
        for provider in ("claude", "opencode"):
            with self.subTest(provider=provider):
                with self.assertRaisesRegex(
                    ProviderConnectionError, "provider_connection_unavailable"
                ):
                    self.service.save_graph_preferences(
                        self.profile,
                        graph,
                        GraphProviderPreferences(**{provider: codex}),
                    )
        records = self.service._records(self.profile)
        self.service._save(
            self.profile, [records[0].model_copy(update={"provider": "claude"})]
        )
        self.service.save_graph_preferences(
            self.profile, graph, GraphProviderPreferences(claude=codex)
        )
        self.assertEqual(
            self.service.graph_preferences(self.profile, graph).claude, codex
        )
        self.assertIsNone(self.service.graph_preferences(self.profile, graph).codex)
        with self.assertRaisesRegex(
            ProviderConnectionError, "provider_connection_unavailable"
        ):
            self.service.save_graph_preferences(
                self.other_profile, graph, GraphProviderPreferences(claude=codex)
            )

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

    def test_other_provider_email_does_not_block_codex_admission(self):
        """Identity equivalence is scoped to the provider, never a display label."""
        first = self.connect("claude-row", email="shared@example.invalid")
        row = self.service._records(self.profile)[0]
        claude = row.model_copy(update={"provider": "claude"})
        go = row.model_copy(
            update={
                "provider": "opencode",
                "connection_id": uuid4(),
                "credential_id": uuid4(),
            }
        )
        self.service._save(self.profile, [claude, go])
        result = self.connect("codex-row", email="shared@example.invalid")
        self.assertEqual(result.status, "connected")
        self.assertNotEqual(result.connection_id, first.connection_id)
        self.assertEqual(len(self.service._records(self.profile)), 3)

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

    def test_new_registration_with_same_email_cannot_create_another_row(self):
        """Email collisions refuse admission without linking separate registrations."""
        existing = self.connect(email="person@example.invalid")
        duplicate = self.connect(
            "different-subject", "oaiapp_another", email="PERSON@example.invalid"
        )
        self.assertEqual(duplicate.status, "duplicate")
        self.assertEqual(duplicate.connection_id, existing.connection_id)
        self.assertEqual(len(self.service.list(self.profile)), 1)
        self.assertEqual(
            self.service.borrow(self.profile, existing.connection_id, 1)[0],
            "one-access",
        )

    def test_same_email_does_not_authorize_replacing_another_subject(self):
        """The row restriction never weakens reconnect's verified subject check."""
        existing = self.connect(email="person@example.invalid")
        result = self.connect(
            "different-subject",
            "oaiapp_one",
            existing.connection_id,
            email="person@example.invalid",
        )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.code, "provider_account_mismatch")
        self.assertEqual(len(self.service.list(self.profile)), 1)
        self.assertEqual(
            self.service.borrow(self.profile, existing.connection_id, 1)[0],
            "one-access",
        )

    def test_email_collision_does_not_block_repairing_an_existing_connection(self):
        """Extra-row refusal never strands an exact saved-account reconnect."""
        existing = self.connect(email="person@example.invalid")
        other = self.connect("two", "oaiapp_two")
        records = self.service._records(self.profile)
        self.service._save(
            self.profile,
            [
                (
                    record.model_copy(update={"label": "person@example.invalid"})
                    if record.connection_id == other.connection_id
                    else record
                )
                for record in records
            ],
        )
        result = self.connect(
            "one",
            "oaiapp_one",
            existing.connection_id,
            email="person@example.invalid",
        )
        self.assertEqual(result.status, "connected")
        self.assertEqual(result.connection_id, existing.connection_id)
        self.assertEqual(len(self.service.list(self.profile)), 2)
        self.assertEqual(
            self.service.borrow(self.profile, existing.connection_id, 2)[0],
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
        pending = self.service.codex.attempts[receipt.attempt_id]
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

    def test_non_ascii_callback_state_is_refused_without_breaking_diagnostics(self):
        """Malformed state has no exchange or uncertain-publication side effect."""
        receipt, _url = self.service.begin(
            self.profile, "http://127.0.0.1:17867/auth/callback"
        )
        for cancelled in (False, True):
            if cancelled:
                self.service.cancel_profile(self.profile)
            with self.assertLogs(
                "laomedo.agents.agents.codex.connection", level="WARNING"
            ) as captured:
                with self.assertRaisesRegex(
                    ProviderConnectionError, "provider_login_expired"
                ):
                    self.service.complete(
                        self.profile, {"state": "\u00e9-private-fixture"}
                    )
            self.assertIn("state_matches=0", " ".join(captured.output))
            self.assertNotIn("private-fixture", " ".join(captured.output))
        self.assertEqual(self.service.list(self.profile), [])

    def test_logout_and_expiry_refuse_callback_replay(self):
        """Neither polling nor a restart can resume invalidated authorizations."""
        receipt, _url = self.service.begin(
            self.profile, "http://127.0.0.1:17867/auth/callback"
        )
        pending = self.service.codex.attempts[receipt.attempt_id]
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
        from laomedo.host.credentials.siwc.utils import _atomic_private

        def fail_metadata(path, value):
            if path.name == "connections.json":
                raise OSError("fixture write failed")
            return _atomic_private(path, value)

        with patch(
            "laomedo.agents.connections.service._atomic_private",
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
        broker = self.service.codex._broker(self.profile, previous.credential_id)
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
        from laomedo.host.credentials.siwc.utils import _atomic_private

        existing = self.connect()

        def uncertain(path, value):
            _atomic_private(path, value)
            if path.name == "connections.json":
                raise OSError("fixture error after publication")

        with patch(
            "laomedo.agents.connections.service._atomic_private",
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
        pending = self.service.codex.attempts[receipt.attempt_id]
        pending.superseded_scrubbed = False
        with patch.object(
            self.service.codex,
            "_scrub",
            side_effect=AssertionError("cancellation must not wait for token cleanup"),
        ):
            result = self.service.cancel(self.profile, receipt.attempt_id)
        self.assertEqual(result.status, "connected")
        self.assertEqual(result.connection_id, existing.connection_id)

    def test_disconnect_fences_before_stop_and_keeps_failed_cleanup_recoverable(self):
        """A stopped controller is required before erasing an admitted local login."""
        existing = self.connect()
        controller = Mock()
        controller.inventory.return_value = (1, 7)
        controller.stop.return_value = False
        self.service.controllers = controller
        info = self.service.disconnect_info(self.profile, existing.connection_id)
        self.assertEqual(info.active_runs, 1)
        progress = self.service.disconnect(
            self.profile, existing.connection_id, info.generation, info.revision
        )
        self.assertEqual(progress.status, "disconnecting")
        with self.assertRaisesRegex(
            ProviderConnectionError, "provider_connection_disconnecting"
        ):
            self.service.borrow(self.profile, existing.connection_id, 1)
        with self.assertRaisesRegex(
            ProviderConnectionError, "provider_connection_disconnecting"
        ):
            self.service.begin(
                self.profile,
                "http://127.0.0.1:17867/auth/callback",
                existing.connection_id,
            )
        controller.stop.return_value = True
        with patch.object(self.service.codex, "_scrub", side_effect=OSError("locked")):
            progress = self.service.retry_cleanup(self.profile, existing.connection_id)
        self.assertEqual(progress.status, "cleanup_required")
        self.assertEqual(
            self.service.list(self.profile)[0].lifecycle, "cleanup_required"
        )
        progress = self.service.retry_cleanup(self.profile, existing.connection_id)
        self.assertEqual(progress.status, "removed")
        self.assertEqual(self.service.list(self.profile), [])

    def test_stale_disconnect_confirmation_preserves_connection(self):
        """Newly admitted work must be disclosed before the user confirms stopping it."""
        existing = self.connect()
        controller = Mock()
        controller.inventory.return_value = (2, 8)
        self.service.controllers = controller
        with self.assertRaisesRegex(
            ProviderConnectionError, "provider_confirmation_changed"
        ):
            self.service.disconnect(self.profile, existing.connection_id, 1, 7)
        controller.stop.assert_not_called()
        self.assertEqual(
            self.service.borrow(self.profile, existing.connection_id, 1)[0],
            "one-access",
        )

    def test_reconnect_waits_for_active_work_instead_of_interrupting_its_account(self):
        """Reauthentication cannot replace credentials underneath an active controller."""
        existing = self.connect()
        controller = Mock()
        controller.inventory.return_value = (1, 2)
        self.service.controllers = controller
        with self.assertRaisesRegex(
            ProviderConnectionError, "provider_connection_busy"
        ):
            self.service.begin(
                self.profile,
                "http://127.0.0.1:17867/auth/callback",
                existing.connection_id,
            )
        self.assertEqual(
            self.service.borrow(self.profile, existing.connection_id, 1)[0],
            "one-access",
        )

    def test_saved_probe_uses_connection_epoch_across_routine_rotation(self):
        """Renewal changes credential evidence without pretending the account was replaced."""
        from laomedo.host.credentials.siwc.utils import _atomic_private
        from laomedo.agents.connections.credentials import (
            SavedConnectionCredential,
        )

        existing = self.connect()
        credential = SavedConnectionCredential(
            self.service, self.profile, existing.connection_id, 1
        )
        before = credential.summary(credential.account(credential.client_id))
        record = self.service._record(self.profile, existing.connection_id)
        broker = self.service.codex._broker(self.profile, record.credential_id)
        account = broker.account(record.client_id)
        account["generation"] += 1
        _atomic_private(broker._path(record.client_id), account)
        after = credential.summary(credential.account(credential.client_id))
        self.assertNotEqual(before["generation"], after["generation"])
        self.assertEqual(
            before["connection_generation"], after["connection_generation"]
        )
        controller = Mock()
        controller.inventory.return_value = (0, 0)
        controller.stop.return_value = False
        self.service.controllers = controller
        self.service.disconnect(self.profile, existing.connection_id, 1, 0)
        with self.assertRaisesRegex(ValueError, "auth_revoked"):
            credential.account(credential.client_id)

    def test_rotation_keeps_the_saved_identity_epoch_without_index_write(self):
        """Routine rotation cannot invalidate a selected connection generation."""
        from laomedo.host.credentials.siwc.connection import ChatGPTConnection
        from laomedo.host.credentials.siwc.utils import _atomic_private

        existing = self.connect()
        record = self.service._record(self.profile, existing.connection_id)
        broker = self.service.codex._broker(self.profile, record.credential_id)
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
        original = self.service.codex._broker(self.profile, record.credential_id)
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
