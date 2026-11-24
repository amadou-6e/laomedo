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

    def test_renewal_keeps_one_revocation_identity_and_expires_aliases(self):
        """Token rotation neither forks a browser lease nor revives logout."""
        with patch("laomedo.agents.connections.service.time.time", return_value=100):
            self.service.renew_lease("original", "renewed", 200)
            self.service.renew_lease("renewed", "again", 300)
            self.assertEqual(self.service.resolve_lease("again"), "original")
            self.service.cancel_lease("renewed")
            for lease in ("original", "renewed", "again"):
                with (
                    self.subTest(lease=lease),
                    self.assertRaises(ProviderConnectionError),
                ):
                    self.service.check_lease(lease)
            with self.assertRaises(ProviderConnectionError):
                self.service.renew_lease("again", "raced-logout", 300)
            with self.assertRaises(ProviderConnectionError):
                self.service.check_lease("raced-logout")
        with patch("laomedo.agents.connections.service.time.time", return_value=400):
            self.assertEqual(self.service.resolve_lease("again"), "again")
            self.assertEqual(self.service._lease_renewals, {})

    def test_conflicting_renewal_revokes_the_collision_without_cross_browser_adoption(
        self,
    ):
        """A duplicate issued digest cannot move an existing browser alias."""
        with patch("laomedo.agents.connections.service.time.time", return_value=100):
            self.service.renew_lease("browser-one", "collision", 200)
            with self.assertRaises(ProviderConnectionError):
                self.service.renew_lease("browser-two", "collision", 200)
            self.assertEqual(self.service.resolve_lease("collision"), "collision")
            with self.assertRaises(ProviderConnectionError):
                self.service.check_lease("collision")
            self.service.check_lease("browser-one")
            self.service.check_lease("browser-two")

    def connect(self, subject="one", client="oaiapp_one", connection_id=None):
        """Seed a retained operational revision; this never exercises retired login.

        Keep borrow/removal coverage until saved token-sharing revisions have all
        been explicitly replaced or disconnected. No graph compatibility promise.
        """
        import hashlib
        import time
        from laomedo.agents.connections.models import ConnectionRecord, LoginProgress
        from laomedo.host.credentials.siwc.utils import _atomic_private

        connection_id = connection_id or uuid4()
        credential_id = uuid4()
        broker = self.service.codex._broker(self.profile, credential_id)
        _atomic_private(
            broker._path(client),
            {
                "client_id": client,
                "subject": subject,
                "issuer": "https://auth.openai.com",
                "email": subject + "@example.invalid",
                "ext_agent_host_id": "fixture",
                "id_token": "fixture-id",
                "access_token": subject + "-access",
                "refresh_token": subject + "-refresh",
                "scopes": sorted(NEEDED),
                "expires_at": time.time() + 3600,
                "generation": 1,
                "state": "active",
            },
        )
        record = ConnectionRecord(
            connection_id=connection_id,
            credential_id=credential_id,
            client_id=client,
            subject_hash=hashlib.sha256(
                ("https://auth.openai.com" + chr(0) + subject).encode()
            ).hexdigest(),
            generation=1,
            label=subject + "@example.invalid",
        )
        self.service._save(self.profile, self.service._records(self.profile) + [record])
        return LoginProgress(
            attempt_id=uuid4(), status="connected", connection_id=connection_id
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
        with patch.object(
            self.service.codex.retained, "_scrub", side_effect=OSError("locked")
        ):
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
