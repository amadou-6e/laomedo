"""Account/epoch/lease isolation for supported subscription quota observations."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from laomedo.agents.agents.base.models import (
    SubscriptionSnapshot,
    SubscriptionBucket,
    SubscriptionWindow,
)
from laomedo.agents.connections.models import ConnectionRecord
from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.errors import RunnerError
from laomedo.agents.connections.quota import SubscriptionObservations
from laomedo.agents.connections.service import ProviderConnections


class SubscriptionObservationTests(unittest.TestCase):
    """Exercise real lifecycle metadata and deterministic read transports, not native acceptance."""

    def setUp(self):
        """Create private isolated account metadata with a controlled clock and native reader."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.service = ProviderConnections(Path(temporary.name) / "connections")
        self.addCleanup(self.service.close)
        self.owner, self.connection = uuid4(), uuid4()
        self.now = 1800000000.0
        self.record = ConnectionRecord(
            connection_id=self.connection,
            credential_id=uuid4(),
            client_id="codex-native",
            subject_hash=hashlib.sha256(b"issuer\0subject").hexdigest(),
            generation=1,
            label="Test account",
        )
        self.service._save(self.owner, [self.record])
        profile = patch.object(self.service.codex, "profile", return_value=Mock())
        self.native_profile = profile.start()
        self.addCleanup(profile.stop)
        identity = patch.object(
            self.service.codex, "saved_identity", return_value=Mock()
        )
        self.native_identity = identity.start()
        self.addCleanup(identity.stop)
        self.snapshot = SubscriptionSnapshot(
            buckets=[
                SubscriptionBucket(
                    limit_id="codex",
                    windows=[
                        SubscriptionWindow(
                            kind="primary",
                            used_percent=25,
                            window_minutes=300,
                            resets_at=int(self.now + 300),
                        )
                    ],
                )
            ]
        )
        self.reader = Mock(return_value=self.snapshot)
        self.controllers = Mock(closed=False, subscription_limits=self.reader)
        self.service.controllers = self.controllers
        self.addCleanup(setattr, self.service, "controllers", None)
        self.quota = SubscriptionObservations(self.service, clock=lambda: self.now)
        self.service.subscriptions = self.quota

    def refresh(self, lease="lease-one"):
        """Refresh the exact owned generation under the requested test browser lease."""
        return self.quota.refresh(self.owner, self.connection, 1, lease)

    def read(self, lease="lease-one"):
        """Read cache only for the exact current account and browser lease."""
        return self.quota.read(self.owner, self.connection, 1, lease)

    def test_mount_is_cache_only_and_explicit_refresh_submits_zero_turns(self):
        self.assertEqual(self.read().state, "not_checked")
        self.reader.assert_not_called()
        result = self.refresh()
        self.assertEqual(result.state, "ready")
        self.assertEqual(result.snapshot.submitted_turns, 0)
        self.assertEqual(result.snapshot.buckets[0].windows[0].used_percent, 25)
        self.assertEqual(self.reader.call_count, 1)
        self.assertEqual(self.refresh().snapshot, result.snapshot)
        self.assertEqual(self.reader.call_count, 1)
        self.native_profile.assert_not_called()

    def test_explicit_native_reader_does_not_hold_lifecycle_lock(self):
        def observe(binding):
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(self.service.check_lease, "independent-lease").result(
                    timeout=2
                )
            return self.snapshot

        self.reader.side_effect = observe
        self.assertEqual(self.refresh().state, "ready")

    def test_shared_fresh_native_cache_requires_explicit_lease_visibility(self):
        self.refresh()
        self.assertEqual(self.read("lease-two").state, "not_checked")
        self.assertEqual(self.refresh("lease-two").state, "ready")
        self.assertEqual(self.reader.call_count, 1)

    def test_logout_erases_only_that_lease_and_refuses_late_publication(self):
        self.refresh()
        self.refresh("lease-two")
        self.service.cancel_lease("lease-one")
        with self.assertRaises(ProviderConnectionError):
            self.read()
        self.assertEqual(self.read("lease-two").state, "ready")

    def test_generation_and_foreign_profile_never_reuse_snapshot(self):
        self.refresh()
        with self.assertRaises(ProviderConnectionError):
            self.quota.read(uuid4(), self.connection, 1, "lease-one")
        self.service._save(
            self.owner, [self.record.model_copy(update={"generation": 2})]
        )
        with self.assertRaises(ProviderConnectionError):
            self.read()
        self.assertEqual(
            self.quota.read(self.owner, self.connection, 2, "lease-one").state,
            "not_checked",
        )

    def test_changed_native_identity_metadata_discards_cached_values(self):
        self.refresh()
        self.native_identity.side_effect = ProviderConnectionError(
            "provider_connection_changed"
        )
        with self.assertRaises(ProviderConnectionError):
            self.read()
        self.assertEqual(len(self.quota.entries), 0)

    def test_retained_token_sharing_login_never_launches_known_unsupported_quota(self):
        self.service._save(
            self.owner,
            [self.record.model_copy(update={"client_id": "retained-client"})],
        )
        self.assertEqual(self.read().reason, "unsupported")
        self.assertEqual(self.refresh().reason, "unsupported")
        self.reader.assert_not_called()

    def test_stale_after_age_or_reset_never_infers_replenishment(self):
        first = self.refresh()
        self.now += 61
        stale = self.read()
        self.assertEqual(stale.state, "stale")
        self.assertEqual(stale.snapshot, first.snapshot)
        self.snapshot = SubscriptionSnapshot(
            buckets=[
                SubscriptionBucket(
                    limit_id="codex",
                    windows=[
                        SubscriptionWindow(
                            kind="primary",
                            used_percent=100,
                            resets_at=int(self.now - 1),
                        )
                    ],
                )
            ]
        )
        self.reader.return_value = self.snapshot
        self.assertEqual(self.refresh().state, "stale")
        self.assertEqual(self.read().snapshot.buckets[0].windows[0].used_percent, 100)

    def test_failed_refresh_preserves_stale_evidence_and_throttles_retries(self):
        first = self.refresh()
        self.now += 61
        self.reader.side_effect = RuntimeError("private provider body must not escape")
        failed = self.refresh()
        self.assertEqual((failed.state, failed.reason), ("stale", "refresh_failed"))
        self.assertEqual(failed.snapshot, first.snapshot)
        self.assertNotIn("private", failed.model_dump_json())
        self.refresh()
        self.assertEqual(self.reader.call_count, 2)
        self.now += 11
        self.refresh()
        self.assertEqual(self.reader.call_count, 3)

    def test_first_failure_and_native_busy_are_unavailable_not_zero(self):
        for error_type in (ProviderConnectionError, RunnerError):
            with self.subTest(error_type=error_type):
                self.quota.invalidate()
                self.reader.side_effect = error_type("provider_connection_busy")
                result = self.refresh()
                self.assertEqual((result.state, result.reason), ("unavailable", "busy"))
                self.assertIsNone(result.snapshot)

    def test_retention_expires_without_native_fetch(self):
        self.refresh()
        self.now += 601
        self.assertEqual(self.read().state, "not_checked")
        self.assertEqual(len(self.quota.entries), 0)
        self.assertEqual(self.reader.call_count, 1)

    def test_disconnect_during_native_read_discards_the_result(self):
        def revoke(binding):
            self.service._save(
                self.owner,
                [
                    self.record.model_copy(
                        update={"lifecycle": "disconnecting", "generation": 2}
                    )
                ],
            )
            return self.snapshot

        self.reader.side_effect = revoke
        with self.assertRaises(ProviderConnectionError):
            self.refresh()
        self.assertEqual(len(self.quota.entries), 0)

    def test_two_browser_leases_share_native_flight_and_one_logout_does_not_poison_other(
        self,
    ):
        entered, release = threading.Event(), threading.Event()

        def observe(binding):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test synchronization timeout")
            return self.snapshot

        self.reader.side_effect = observe
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.refresh)
            self.assertTrue(entered.wait(2))
            second = pool.submit(self.refresh, "lease-two")
            self.service.cancel_lease("lease-one")
            release.set()
            with self.assertRaises(ProviderConnectionError):
                first.result(timeout=5)
            self.assertEqual(second.result(timeout=5).state, "ready")
        self.assertEqual(self.reader.call_count, 1)

    def test_closed_owner_and_empty_lease_cannot_read(self):
        self.refresh()
        with self.assertRaises(ProviderConnectionError):
            self.read("")
        self.controllers.closed = True
        with self.assertRaises(ProviderConnectionError):
            self.read()
