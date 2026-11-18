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

    def test_saved_native_auth_never_mirrors_host_login(self):
        """Even an operator mirror opt-in cannot replace a saved account's profile."""
        guard = Mock()
        agent = SimpleNamespace(auth_connection=guard)
        with patch("laomedo.agents.agents.claude.credentials.mirror_login") as mirror:
            result = ClaudeCredentialProvider(agent).prepare(CredentialRequest())
        guard.check.assert_called_once_with()
        mirror.assert_not_called()
        self.assertEqual(result.credential_mode, "dedicated_volume")

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
