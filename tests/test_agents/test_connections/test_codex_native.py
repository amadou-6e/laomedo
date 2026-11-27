"""Native login lifecycle fixtures; these do not establish real provider acceptance."""

import json
from importlib.util import find_spec
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, skipUnless
from unittest.mock import MagicMock, patch
from uuid import uuid4

from laomedo.agents.agents.codex.models import CodexLoginAttempt
from laomedo.agents.connections.models import (
    ConnectionRecord,
    GraphProviderPreferences,
    LoginProgress,
)
from laomedo.agents.connections.service import ProviderConnections


class CodexNativeLoginTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = ProviderConnections(Path(self.temp.name) / "connections")
        self.addCleanup(self.service.close)
        self.profile = uuid4()
        self.adapter = self.service.codex
        self.identity = {
            "type": "identity",
            "email": "new@example.invalid",
            "account_id": "workspace_1",
            "plan_type": "plus",
        }
        self.session = MagicMock()
        self.session.wait.return_value = 0
        self.session.stop_on.return_value.__enter__.return_value = None
        self.runtime = patch("laomedo.agents.agents.codex.connection.DockerRuntime")
        runtime = self.runtime.start()
        self.addCleanup(self.runtime.stop)
        runtime.session.return_value.__enter__.return_value = self.session
        runtime.ensure_image.return_value = "sha256:" + "a" * 64
        self.custody_patch = patch(
            "laomedo.agents.agents.codex.connection.CodexNativeCredentials"
        )
        self.custody_type = self.custody_patch.start()
        self.addCleanup(self.custody_patch.stop)
        self.custody = self.custody_type.return_value
        self.custody.lease.return_value.__enter__.return_value = SimpleNamespace()
        self.custody.create.side_effect = self.mark_custody
        if find_spec("py_docker"):
            from py_docker.containers.models import ContainerSpec

            self.adapter.spec = MagicMock(
                return_value=ContainerSpec(
                    image="sha256:" + "a" * 64, name="fixture-auth"
                )
            )

    def mark_custody(self, *args):
        root = self.adapter._root(self.profile, self.item.credential_id)
        (root / "codex-custody.json").write_text("{}")

    def attempt(self, previous=None):
        self.item = CodexLoginAttempt(
            profile_id=self.profile,
            lease_hash="browser",
            candidate_id=previous.connection_id if previous else uuid4(),
            credential_id=uuid4(),
            previous=previous,
            expires_at=time.monotonic() + 10,
            progress=LoginProgress(attempt_id=uuid4(), status="connecting"),
            cancelled=threading.Event(),
            ready=threading.Event(),
            confirmation=threading.Event(),
        )
        self.adapter.attempts[self.item.progress.attempt_id] = self.item
        return self.item

    def frames(self, identity=None):
        values = [
            {
                "type": "device",
                "authorization_url": "https://auth.openai.com/codex/device",
                "user_code": "ABCD-1234",
            },
            identity or self.identity,
        ]
        self.session.read_frame.side_effect = [
            SimpleNamespace(data=(json.dumps(v) + "\n").encode()) for v in values
        ] + [None]

    def previous(self):
        record = ConnectionRecord(
            connection_id=uuid4(),
            credential_id=uuid4(),
            client_id="saved-siwc",
            subject_hash="old-identity",
            generation=4,
            label="old@example.invalid",
        )
        self.service._save(self.profile, [record])
        return record

    @skipUnless(find_spec("py_docker"), "Requires the optional Docker SDK")
    def test_new_login_publishes_only_after_confirmed_native_teardown(self):
        item = self.attempt()
        self.frames()
        self.adapter._run(item)
        saved = self.service.admitted(self.profile, item.candidate_id)
        self.assertEqual(saved.client_id, "codex-native")
        self.assertEqual(saved.generation, 1)
        self.assertEqual(item.progress.status, "connected")
        self.custody.erase.assert_not_called()

    @skipUnless(find_spec("py_docker"), "Requires the optional Docker SDK")
    def test_replacement_requires_confirmation_and_preserves_graph_selector(self):
        previous = self.previous()
        graph = uuid4()
        self.service.save_graph_preferences(
            self.profile, graph, GraphProviderPreferences(codex=previous.connection_id)
        )
        item = self.attempt(previous)
        self.frames()
        with patch.object(self.adapter, "erase_revision") as erase:
            worker = threading.Thread(target=self.adapter._run, args=(item,))
            worker.start()
            self.addCleanup(lambda: (item.cancelled.set(), worker.join(3)))
            deadline = time.monotonic() + 3
            while item.progress.status == "connecting" and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(item.progress.status, "awaiting_confirmation")
            self.assertEqual(
                self.service.admitted(self.profile, item.candidate_id), previous
            )
            details = self.adapter.details(
                self.profile, item.progress.attempt_id, lease_hash="browser"
            )
            self.assertEqual(
                details["replacement_account"]["email"], self.identity["email"]
            )
            self.assertIsNone(details["user_code"])
            self.adapter.confirm(
                self.profile, item.progress.attempt_id, lease_hash="browser"
            )
            worker.join(3)
            self.assertFalse(worker.is_alive())
            saved = self.service.admitted(self.profile, item.candidate_id)
            self.assertEqual(saved.generation, 5)
            self.assertEqual(saved.connection_id, previous.connection_id)
            self.assertEqual(
                self.service.graph_preferences(self.profile, graph).codex,
                previous.connection_id,
            )
            erase.assert_called_once_with(self.profile, previous)

    @skipUnless(find_spec("py_docker"), "Requires the optional Docker SDK")
    def test_cancellation_after_native_completion_discards_candidate_and_preserves_old(
        self,
    ):
        previous = self.previous()
        item = self.attempt(previous)
        self.frames()
        worker = threading.Thread(target=self.adapter._run, args=(item,))
        worker.start()
        deadline = time.monotonic() + 3
        while item.progress.status == "connecting" and time.monotonic() < deadline:
            time.sleep(0.01)
        self.adapter.cancel(self.profile, item.progress.attempt_id)
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(
            self.service.admitted(self.profile, item.candidate_id), previous
        )
        self.custody.erase.assert_called_once()
        self.assertEqual(item.progress.status, "cancelled")

    @skipUnless(find_spec("py_docker"), "Requires the optional Docker SDK")
    def test_unknown_native_output_never_publishes_or_leaks_raw_error(self):
        item = self.attempt()
        self.frames({"type": "failed", "code": "private-native-detail"})
        self.adapter._run(item)
        self.assertEqual(item.progress.code, "provider_sign_in_failed")
        self.assertEqual(self.service._records(self.profile), [])
        self.custody.erase.assert_called_once()
        self.assertNotIn("private-native-detail", item.progress.model_dump_json())

    def test_device_details_require_originating_lease_and_generic_progress_has_no_code(
        self,
    ):
        item = self.attempt()
        item.user_code = __import__("pydantic").SecretStr("ABCD-1234")
        from laomedo.agents.connections.errors import ProviderConnectionError

        with self.assertRaises(ProviderConnectionError):
            self.adapter.details(
                self.profile, item.progress.attempt_id, lease_hash="another-browser"
            )
        self.assertNotIn(
            "ABCD-1234",
            self.adapter.progress(
                self.profile, item.progress.attempt_id
            ).model_dump_json(),
        )
