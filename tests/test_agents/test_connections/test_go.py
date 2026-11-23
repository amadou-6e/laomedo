"""Go key custody and dispatch boundaries; not upstream authentication acceptance."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from uuid import uuid4

from pydantic import SecretStr

from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.connections.models import GraphProviderPreferences
from laomedo.agents.connections.service import ProviderConnections


class GoConnectionTests(unittest.TestCase):
    """Protect private independent keys, honest identity and confirmed cleanup."""

    def setUp(self):
        """Create a disposable private store without reading any real login."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "providers"
        self.service = ProviderConnections(self.root)
        self.addCleanup(self.service.close)
        self.profile = uuid4()

    def test_save_duplicate_and_restart_keep_exact_key_ownership(self):
        """Only exact repeated keys deduplicate; labels never prove identity."""
        one, duplicate = self.service.go.save(
            self.profile, SecretStr("fixture-key-one"), "Work"
        )
        two, _ = self.service.go.save(
            self.profile, SecretStr("fixture-key-two"), "Work"
        )
        self.assertFalse(duplicate)
        repeated, duplicate = self.service.go.save(
            self.profile, SecretStr("fixture-key-one"), "Different label"
        )
        self.assertTrue(duplicate)
        self.assertEqual(repeated.connection_id, one.connection_id)
        self.assertNotEqual(one.connection_id, two.connection_id)
        self.assertEqual(one.auth_state, "unavailable")
        public = json.dumps(
            [row.model_dump(mode="json") for row in self.service.list(self.profile)]
        )
        self.assertNotIn("fixture-key", public)
        self.assertNotIn("credential_id", public)
        self.assertEqual(self.service.list(uuid4()), [])
        graph = uuid4()
        self.service.save_graph_preferences(
            self.profile, graph, GraphProviderPreferences(opencode=one.connection_id)
        )
        with self.assertRaises(ProviderConnectionError):
            self.service.save_graph_preferences(
                self.profile, graph, GraphProviderPreferences(codex=one.connection_id)
            )
        with self.assertRaises(ProviderConnectionError):
            self.service.borrow(self.profile, one.connection_id, 1)
        self.service.close()
        self.service = ProviderConnections(self.root)
        self.addCleanup(self.service.close)
        self.assertEqual(len(self.service.list(self.profile)), 2)
        record = self.service._record(self.profile, one.connection_id)
        profile = self.service.go.profile(self.profile, record)
        self.assertEqual(
            json.loads((profile / "auth.json").read_text())["opencode-go"]["key"],
            "fixture-key-one",
        )

    def test_failed_stop_retains_fenced_key_until_cleanup_is_confirmed(self):
        """A disconnect cannot erase a key still used by an unsettled controller."""
        one, _ = self.service.go.save(
            self.profile, SecretStr("fixture-key-one"), "Work"
        )
        record = self.service._record(self.profile, one.connection_id)
        profile = self.service.go.profile(self.profile, record)
        staged = profile / ("controller-" + "a" * 32)
        staged.mkdir()
        (staged / "config.json").write_text("dead scoped fixture capability")
        unrelated = profile / "controller-not-owned"
        unrelated.mkdir()
        controller = Mock()
        self.service.controllers = controller
        controller.inventory.return_value = (1, 7)
        controller.stop.side_effect = ProviderConnectionError(
            "provider_cleanup_unconfirmed"
        )
        result = self.service.disconnect(self.profile, one.connection_id, 1, 7)
        self.assertEqual(result.status, "cleanup_required")
        self.assertTrue((profile / "auth.json").exists())
        self.assertTrue(staged.exists())
        with self.assertRaises(ProviderConnectionError):
            self.service.admitted(self.profile, one.connection_id)
        controller.stop.side_effect = None
        controller.stop.return_value = True
        self.assertEqual(
            self.service.retry_cleanup(self.profile, one.connection_id).status,
            "removed",
        )
        self.assertFalse((profile / "auth.json").exists())
        self.assertFalse(staged.exists())
        self.assertTrue(unrelated.exists())
        self.assertEqual(self.service.list(self.profile), [])

    def test_interrupted_publication_scrubs_only_unadmitted_go_key(self):
        """Restart removes crash-left key material without changing admitted keys."""
        one, _ = self.service.go.save(
            self.profile, SecretStr("fixture-key-one"), "Work"
        )
        record = self.service._record(self.profile, one.connection_id)
        extra = self.service._profile(self.profile) / str(uuid4())
        extra.mkdir()
        (extra / "go-custody.json").write_text("{}")
        pending = extra / ("auth.json.pending-" + "a" * 32)
        pending.write_text("fixture-secret")
        self.service.close()
        self.service = ProviderConnections(self.root)
        self.addCleanup(self.service.close)
        self.assertFalse(pending.exists())
        self.assertTrue(
            (self.service.go.profile(self.profile, record) / "auth.json").exists()
        )
