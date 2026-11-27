"""Current native credential custody: one writer, exact recovery, no token reads."""

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import MagicMock, patch

from laomedo.agents.agents.codex.native import CodexNativeCredentials
from laomedo.agents.connections.errors import ProviderConnectionError


class NativeCredentialTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.credentials = CodexNativeCredentials(self.root)
        (self.root / "codex-custody.json").write_text(
            json.dumps(
                {
                    "name": "laomedo-codex-connection-" + "a" * 32,
                    "labels": {"owner": "opaque"},
                    "docker_endpoint": "unix:///original.sock",
                    "image_id": "sha256:" + "b" * 64,
                }
            )
        )
        self.docker = MagicMock()
        self.client = patch.object(CodexNativeCredentials, "_client")
        client = self.client.start()
        client.return_value.__enter__.return_value = self.docker
        self.addCleanup(self.client.stop)
        self.identity = patch.object(
            CodexNativeCredentials, "_identity", return_value="owned"
        )
        self.identity.start()
        self.addCleanup(self.identity.stop)

    def test_second_writer_is_busy_until_lease_exits(self):
        second = CodexNativeCredentials(self.root)
        with self.credentials.lease():
            with self.assertRaises(ProviderConnectionError) as failure:
                with second.lease():
                    self.fail("A second writer was admitted")
            self.assertEqual(failure.exception.code, "provider_connection_busy")
        with second.lease() as profile:
            self.assertEqual(profile.docker_endpoint, "unix:///original.sock")

    def test_writer_lock_fences_a_separate_process(self):
        script = """
from pathlib import Path
import sys
from unittest.mock import patch
from laomedo.agents.agents.codex.native import CodexNativeCredentials
from laomedo.agents.connections.errors import ProviderConnectionError
credentials = CodexNativeCredentials(Path(sys.argv[1]))
with patch.object(CodexNativeCredentials, '_client'):
    try:
        with credentials.lease(require_volume=False):
            print('admitted')
    except ProviderConnectionError as error:
        print(error.code)
"""
        command = [sys.executable, "-c", script, str(self.root)]
        with self.credentials.lease():
            blocked = subprocess.run(
                command, capture_output=True, text=True, check=True, timeout=30
            )
        self.assertEqual(blocked.stdout.strip(), "provider_connection_busy")
        admitted = subprocess.run(
            command, capture_output=True, text=True, check=True, timeout=30
        )
        self.assertEqual(admitted.stdout.strip(), "admitted")

    def test_registered_receipt_recovered_before_next_writer(self):
        receipt = self.root / "exact-session.json"
        with self.credentials.lease():
            self.credentials.register(receipt)
            receipt.write_text("creator receipt")
        with patch(
            "laomedo.agents.agents.codex.native.DockerRuntime.recover_receipts"
        ) as recover:
            with CodexNativeCredentials(self.root).lease():
                recover.assert_called_once_with(self.docker, [receipt], kind="session")
        self.assertEqual(
            json.loads((self.root / "native-receipts.json").read_text()),
            {"receipts": []},
        )

    def test_failed_recovery_preserves_custody_and_refuses_admission(self):
        receipt = self.root / "exact-job.json"
        with self.credentials.lease():
            self.credentials.register(receipt, kind="job")
            receipt.write_text("creator receipt")
        with patch(
            "laomedo.agents.agents.codex.native.DockerRuntime.recover_receipts",
            side_effect=RuntimeError("outage"),
        ):
            with self.assertRaises(RuntimeError):
                with self.credentials.lease():
                    self.fail("Unconfirmed client cleanup was ignored")
        self.assertTrue((self.root / "codex-custody.json").exists())
        self.assertEqual(
            len(
                json.loads((self.root / "native-receipts.json").read_text())["receipts"]
            ),
            1,
        )

    def test_missing_profile_is_not_recreated_but_can_finish_erasure(self):
        self.docker.volumes.inspect.return_value = None
        with self.assertRaises(ProviderConnectionError) as failure:
            self.credentials.profile()
        self.assertEqual(failure.exception.code, "provider_connection_unavailable")
        self.credentials.erase()
        self.assertFalse((self.root / "codex-custody.json").exists())
        self.docker.sdk.volumes.create.assert_not_called()

    def test_receipt_registration_requires_live_writer_custody(self):
        with self.assertRaises(ProviderConnectionError):
            self.credentials.register(self.root / "session.json")

    def test_malformed_receipt_registry_is_not_treated_as_empty(self):
        (self.root / "native-receipts.json").write_text(
            '{"receipts": [{"kind": "job", "path": "relative.json"}]}'
        )
        with self.assertRaises(ProviderConnectionError) as failure:
            with self.credentials.lease():
                self.fail("Invalid custody was admitted")
        self.assertEqual(failure.exception.code, "provider_cleanup_unconfirmed")
