"""Synthetic CLI composition checks for separately launched host services."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from laomedo import lease_service, mediation_service
from laomedo.github_git_transport import PushOutcomeUnknown
from laomedo.github_mediation import MediationStore


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
        self.assertRegex(status["instance"], r"^[0-9a-f]{32}$")
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

    def test_provider_journal_counts_attempts_without_secret_payload(self):
        journal = self.path / "attempts.jsonl"
        transport = mediation_service.JournaledTransport(
            lambda repository, operation, payload, **binding:
            {"accepted": True}, journal)
        result = transport("example/disposable", "git_push", {
            "branch": "probe-a", "commit": "a" * 40,
            "secret": "synthetic-provider-secret"},
            connection_id="selected", connection_generation=1)
        self.assertEqual(result, {"accepted": True})
        events = [json.loads(line) for line in journal.read_text(
            encoding="utf-8").splitlines()]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["branch"], "probe-a")
        self.assertNotIn("synthetic-provider-secret", json.dumps(events))

    def test_nonzero_push_diagnostic_is_fixed_vocabulary_and_stays_unknown(self):
        attempts = self.path / "attempts.jsonl"
        diagnostics = self.path / "diagnostics.jsonl"

        def nonzero_push(*_args, **_kwargs):
            raise PushOutcomeUnknown("authentication_or_authorization", 1)

        journal = mediation_service.JournaledTransport(
            nonzero_push, attempts, diagnostics)
        store = MediationStore(
            self.path / "effects.sqlite",
            workflow_change_classifier=lambda *_args: False)
        _, bearer = store.issue(
            run_id="run-a", invocation_id="invocation-a",
            repository="example/disposable", branch="probe-a",
            operations={"git_push"}, ttl_seconds=60)
        payload = {"branch": "probe-a", "commit": "a" * 40}
        first = store.invoke(
            token=bearer, repository="example/disposable",
            operation="git_push", payload=payload, effect_id="push-a",
            transport=journal)
        second = store.invoke(
            token=bearer, repository="example/disposable",
            operation="git_push", payload=payload, effect_id="push-a",
            transport=journal)
        self.assertEqual(first, {"state": "unknown", "resent": False})
        self.assertEqual(second, first)
        self.assertEqual(len(attempts.read_text(encoding="utf-8").splitlines()), 1)
        diagnostic = json.loads(diagnostics.read_text(encoding="utf-8"))
        self.assertEqual(diagnostic["category"],
                         "authentication_or_authorization")
        self.assertEqual(diagnostic["exit_code"], 1)
        self.assertNotIn("synthetic-provider-secret", json.dumps(diagnostic))
        self.assertNotIn(bearer, json.dumps(diagnostic))


if __name__ == "__main__":
    unittest.main()
