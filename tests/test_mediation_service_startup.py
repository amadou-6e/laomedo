"""Synthetic CLI composition checks for separately launched host services."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from laomedo import lease_service, mediation_service


class MediationServiceStartupTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.path = Path(self.root.name)
        self.checkout = self.path / "checkout"
        self.checkout.mkdir()
        self.agent_mount = self.path / "agent"
        self.agent_mount.mkdir()
        self.token_file = self.path / "private.env"
        self.token_file.write_text("GH=synthetic-provider-secret\n", encoding="utf-8")
        self.state = self.path / "private-state"

    def test_credential_owner_starts_from_explicit_file_not_ambient_login(self):
        def serve(instance):
            self.assertEqual(instance.server.server_address[0], "127.0.0.1")

        def close(instance):
            instance.server.server_close()

        args = ["mediation_service", "--state", str(self.state),
                "--repository", "example/disposable",
                "--checkout", str(self.checkout), "--baseline", "a" * 40,
                "--agent-mount", str(self.agent_mount),
                "--connection-id", "selected", "--connection-generation", "1",
                "--token-file", str(self.token_file)]
        with patch.object(sys, "argv", args), patch.object(
                mediation_service.MediationHTTPService, "serve", serve), patch.object(
                mediation_service.MediationHTTPService, "close", close):
            mediation_service.main()
        status = json.loads((self.state / "mediator.json").read_text(encoding="utf-8"))
        self.assertEqual(status["connection_id"], "selected")
        self.assertNotIn("synthetic-provider-secret", json.dumps(status))

    def test_lease_service_requires_explicit_mediated_configuration(self):
        seen = []

        def serve(instance):
            seen.append(instance)
            instance.server.server_close()

        args = ["lease_service", "serve", "--state", str(self.state / "lease"),
                "--mediator-store", str(self.state / "mediator.sqlite"),
                "--authority-store", str(self.state / "authority.sqlite"),
                "--repository", "example/disposable",
                "--connection-id", "selected", "--connection-generation", "1"]
        with patch.object(sys, "argv", args), patch.object(
                lease_service.LeaseService, "serve", serve):
            lease_service.main()
        self.assertIsNotNone(seen[0].mediator)
        self.assertIsNotNone(seen[0].mediation_authority)
        self.assertEqual(seen[0].server.server_address[0], "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
