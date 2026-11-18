"""Native Claude ownership checks; these fixtures do not establish real sign-in."""

import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from pydantic import SecretStr

from laomedo.agents.agents.base.models import CredentialRequest
from laomedo.agents.agents.claude.credentials import ClaudeCredentialProvider
from laomedo.agents.errors import RunnerError
from laomedo.host.provider_connections.credentials import SavedClaudeConnection
from laomedo.host.provider_connections.errors import ProviderConnectionError
from laomedo.host.provider_connections.models import ClaudeAccountIdentity
from laomedo.host.provider_connections.models import ClaudeLoginAttempt
from laomedo.host.provider_connections.models import ConnectionRecord
from laomedo.host.provider_connections.models import LoginProgress
from laomedo.host.provider_connections.service import ProviderConnections


class ClaudeConnectionTests(unittest.TestCase):
    """Protect native identity, lease fences and the absence of ambient mirroring."""

    def setUp(self):
        """Create isolated custody without loading any provider credentials."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.service = ProviderConnections(Path(temporary.name) / "providers")
        self.addCleanup(self.service.close)
        self.profile = uuid4()

    def test_uncertain_volume_create_keeps_exact_prior_ownership_receipt(self):
        """Restart can recover an ambiguous creation without adopting other volumes."""
        candidate = SimpleNamespace(candidate_id=uuid4(), credential_id=uuid4())
        root = self.service._profile(self.profile) / str(candidate.credential_id)
        root.mkdir()
        docker = Mock()
        docker.connection.endpoint = "npipe:////./pipe/docker_engine"
        docker.sdk.volumes.create.side_effect = OSError("lost creation reply")
        with self.assertRaises(OSError):
            self.service.claude._create_profile(
                root, docker, candidate, "sha256:" + "a" * 64
            )
        descriptor = self.service.claude._descriptor(root)
        self.assertEqual(
            docker.sdk.volumes.create.call_args.kwargs,
            {
                "name": descriptor.name,
                "labels": descriptor.labels,
            },
        )
        self.assertEqual(
            descriptor.labels["laomedo.connection"], str(candidate.candidate_id)
        )

    def test_slow_native_summary_does_not_block_logout_fence(self):
        """A stalled daemon read cannot retain the browser's ability to dispatch."""
        record = ConnectionRecord(
            provider="claude",
            connection_id=uuid4(),
            credential_id=uuid4(),
            client_id="claude-native",
            subject_hash="a" * 64,
            generation=1,
            label="work@example.invalid",
        )
        self.service._save(self.profile, [record])
        entered, release, fenced = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )

        def summary(*args):
            entered.set()
            release.wait(3)
            return Mock()

        with patch.object(self.service.claude, "summary", side_effect=summary):
            reader = threading.Thread(target=self.service.list, args=(self.profile,))
            reader.start()
            self.assertTrue(entered.wait(1))

            def logout():
                self.service.cancel_lease("browser")
                fenced.set()

            closer = threading.Thread(target=logout)
            closer.start()
            try:
                self.assertTrue(fenced.wait(1))
            finally:
                release.set()
                reader.join(3)
                closer.join(3)
        self.assertIn("browser", self.service.revoked_leases)

    def test_saved_native_auth_never_mirrors_host_login(self):
        """Even an operator mirror opt-in cannot replace a saved account's profile."""
        guard = Mock()
        agent = SimpleNamespace(auth_connection=guard)
        with patch("laomedo.agents.agents.claude.credentials.mirror_login") as mirror:
            result = ClaudeCredentialProvider(agent).prepare(CredentialRequest())
        guard.check.assert_called_once_with()
        mirror.assert_not_called()
        self.assertEqual(result.credential_mode, "dedicated_volume")

    def test_shutdown_returns_while_retaining_custody_for_a_stalled_worker(self):
        """A slow daemon cannot hang shutdown or release a still-active store lease."""
        release = threading.Event()
        worker = threading.Thread(target=release.wait, daemon=True)
        worker.start()
        item = SimpleNamespace(worker=worker, cancelled=threading.Event())
        self.service.claude.attempts[uuid4()] = item
        try:
            with patch(
                "laomedo.host.provider_connections.service.NATIVE_AUTH_CLEANUP_SECONDS",
                0.01,
            ):
                self.service.close()
            self.assertTrue(item.cancelled.is_set())
            self.assertTrue(worker.is_alive())
            self.assertIsNotNone(self.service._ownership)
            with self.assertRaises(ProviderConnectionError):
                self.service._profile(self.profile)
        finally:
            release.set()
            worker.join(1)
            deadline = time.monotonic() + 2
            while self.service._ownership is not None and time.monotonic() < deadline:
                time.sleep(0.01)
        self.assertIsNone(self.service._ownership)

    def test_native_identity_and_generation_are_checked_before_use(self):
        """Another native principal or a reconnected epoch cannot resume this account."""
        identity = ClaudeAccountIdentity(
            email="work@example.invalid", organization_id="org-work"
        )
        record = ConnectionRecord(
            provider="claude",
            connection_id=uuid4(),
            credential_id=uuid4(),
            client_id="claude-native",
            subject_hash=identity.subject_hash(),
            generation=1,
            label=identity.email,
        )
        self.service._save(self.profile, [record])
        self.service.controllers = SimpleNamespace(closed=False)
        saved = SavedClaudeConnection(
            self.service, self.profile, record.connection_id, 1
        )
        with patch.object(self.service.claude, "profile", return_value=Mock()):
            saved.validate({"email": "WORK@example.invalid", "orgId": "org-work"})
            with self.assertRaisesRegex(RunnerError, "provider_connection_changed"):
                saved.validate({"email": "other@example.invalid", "orgId": "org-work"})
            self.service._save(
                self.profile, [record.model_copy(update={"generation": 2})]
            )
            with self.assertRaisesRegex(RunnerError, "provider_connection_changed"):
                saved.check()

    def test_one_use_code_is_bound_to_profile_and_browser_lease(self):
        """A known attempt ID cannot authorize another profile or a signed-out lease."""
        attempt_id = uuid4()
        item = ClaudeLoginAttempt(
            profile_id=self.profile,
            lease_hash="own-lease",
            candidate_id=uuid4(),
            credential_id=uuid4(),
            expires_at=time.monotonic() + 60,
            progress=LoginProgress(
                attempt_id=attempt_id, provider="claude", status="connecting"
            ),
            cancelled=threading.Event(),
            ready=threading.Event(),
            session=Mock(),
        )
        self.service.claude.attempts[attempt_id] = item
        with self.assertRaises(ProviderConnectionError):
            self.service.claude.submit(
                uuid4(), attempt_id, SecretStr("fixture-code"), lease_hash="own-lease"
            )
        with self.assertRaises(ProviderConnectionError):
            self.service.claude.submit(
                self.profile,
                attempt_id,
                SecretStr("fixture-code"),
                lease_hash="other-lease",
            )
        result = self.service.claude.submit(
            self.profile, attempt_id, SecretStr("fixture-code"), lease_hash="own-lease"
        )
        self.assertEqual(result.status, "verifying")
        item.session.write.assert_called_once_with(b"fixture-code\n")
        public = json.dumps(self.service.claude.details(self.profile, attempt_id))
        self.assertNotIn("fixture-code", public)
        with self.assertRaises(ProviderConnectionError):
            self.service.claude.submit(
                self.profile,
                attempt_id,
                SecretStr("fixture-code"),
                lease_hash="own-lease",
            )
        self.service.cancel_lease("own-lease")
        self.assertTrue(item.cancelled.is_set())
        self.assertEqual(item.progress.status, "cancelled")
