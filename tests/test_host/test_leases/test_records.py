"""Independent record projections and boundary values; internal regressions."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib
import json

from laomedo.host.leases.models import ContainerIdentity
from laomedo.host.leases.models import GrantWindow
from laomedo.host.leases.models import LeaseClock
from laomedo.host.leases.models import LeaseGrant
from laomedo.host.leases.models import LeaseRevocationRecord
from laomedo.host.leases.grants import GrantBook
from support.model_assertions import assert_secrets_excluded


class LeaseRecordTests(unittest.TestCase):
    """Keep literal expected records independent of production serializers."""

    def test_container_identity_only_unwraps_in_private_registration(self):
        identity = ContainerIdentity(
            name="container", run_id="run", token="private-lease"
        )
        assert_secrets_excluded(self, identity, ("private-lease",))
        expected = dict(
            name="container",
            run_id="run",
            token="private-lease",
            runner_pid=123,
            created_at=4,
            mediation=None,
        )
        self.assertEqual(
            identity.registration(runner_pid=123, created_at=4, mediation=None),
            expected,
        )
        self.assertNotIn("docker_endpoint", expected)
        restored = ContainerIdentity.from_registration(expected)
        self.assertIsNone(restored.docker_endpoint)

    def test_lease_window_expiry_rollback_renewal_and_revocation(self):
        window = GrantWindow(
            clock=LeaseClock(wall=100, monotonic=10),
            wall_deadline=120,
            monotonic_deadline=30,
        )
        grant = LeaseGrant.from_window("grant", "private-lease", window)
        self.assertEqual(
            (grant.expires_at, grant.issued_monotonic, grant.expires_monotonic),
            (120, 10, 30),
        )
        assert_secrets_excluded(self, grant, ("private-lease",))
        self.assertTrue(grant.bound_to("private-lease"))
        self.assertFalse(grant.bound_to("other"))
        for wall, monotonic, accepted in (
            (119, 29, True),
            (120, 29, False),
            (119, 30, False),
            (90, 9, False),
            (90, 10, True),
        ):
            with self.subTest(wall=wall, monotonic=monotonic):
                self.assertEqual(
                    grant.accepts(LeaseClock(wall=wall, monotonic=monotonic)), accepted
                )
        grant.renew(
            GrantWindow(
                clock=LeaseClock(wall=110, monotonic=20),
                wall_deadline=200,
                monotonic_deadline=200,
            )
        )
        self.assertEqual(
            (grant.expires_at, grant.issued_monotonic, grant.expires_monotonic),
            (160, 10, 70),
        )
        grant.revoke(115)
        self.assertFalse(grant.accepts(LeaseClock(wall=116, monotonic=21)))

    def test_grant_book_scope_renewal_and_denial_audit_match_old_rules(self):
        with TemporaryDirectory() as temporary:
            events = Path(temporary) / "events.jsonl"
            book = GrantBook(events)
            with (
                patch(
                    "laomedo.host.leases.grants.secrets.token_hex",
                    side_effect=["private-grant", "safe-id"],
                ),
                patch("laomedo.host.leases.grants.time.monotonic", return_value=10),
            ):
                grant_id, secret = book.issue("private-lease", 100, 200, 200)
            self.assertEqual((grant_id, secret), ("grant-safe-id", "private-grant"))
            grant = book.by_digest[hashlib.sha256(secret.encode()).hexdigest()]
            with patch("laomedo.host.leases.grants.time.monotonic", return_value=20):
                book.renew("other-parent", 110, 200, 200)
                self.assertEqual((grant.expires_at, grant.expires_monotonic), (150, 60))
                book.renew("private-lease", 110, 200, 200)
                self.assertEqual((grant.expires_at, grant.expires_monotonic), (160, 70))
            for wall, monotonic, accepted in (
                (120, 30, True),
                (90, 9, False),
                (160, 30, False),
                (120, 70, False),
            ):
                with (
                    patch("laomedo.host.leases.grants.time.time", return_value=wall),
                    patch(
                        "laomedo.host.leases.grants.time.monotonic",
                        return_value=monotonic,
                    ),
                ):
                    self.assertEqual(book.check(secret), (accepted, grant_id))
            # Expired grants cannot be revived through book renewal.
            with patch("laomedo.host.leases.grants.time.monotonic", return_value=70):
                book.renew("private-lease", 150, 300, 300)
            self.assertEqual((grant.expires_at, grant.expires_monotonic), (160, 70))
            self.assertEqual(book.revoke("other-parent", 120), [])
            self.assertEqual(book.revoke("private-lease", 120), [grant_id])
            self.assertEqual(book.revoke("private-lease", 121), [])
            with (
                patch("laomedo.host.leases.grants.time.time", return_value=121),
                patch("laomedo.host.leases.grants.time.monotonic", return_value=31),
            ):
                self.assertEqual(book.check(secret), (False, grant_id))
                self.assertEqual(book.check("unknown"), (False, None))
            observations = [
                json.loads(line)
                for line in events.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                observations[-1], dict(at=121, grant_id=None, accepted=False)
            )
            for secret_value in ("private-lease", "private-grant"):
                self.assertNotIn(secret_value, events.read_text(encoding="utf-8"))

    def test_revocation_preserves_omitted_and_explicit_null_evidence(self):
        values = dict(
            reason="lost",
            revoked_grants=["grant"],
            detected_at=1,
            revoked_at=2,
            detected_at_monotonic=10,
            revoked_at_monotonic=11,
        )
        self.assertEqual(LeaseRevocationRecord(**values).to_record(), values)
        complete = {
            **values,
            "cleanup_finished_at": None,
            "cleanup_finished_at_monotonic": None,
            "cleanup_verified": False,
            "state": {"observed": "unknown"},
        }
        self.assertEqual(LeaseRevocationRecord(**complete).to_record(), complete)
