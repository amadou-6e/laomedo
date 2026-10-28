"""Internal preflight controls; real Docker/agent acceptance is recorded separately."""

import ast
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from laomedo.agents.providers.codex.preflight.models import DockerSelection
from laomedo.agents.providers.codex.preflight.service import CodexPreflight
from laomedo.agents.runtime.errors import RunnerError

ROOT = Path(__file__).resolve().parents[1]


class PreflightBoundaryTests(unittest.TestCase):
    """Protect import and public-error boundaries independently of Docker access."""

    def test_host_sdk_is_optional_and_not_imported_by_core_boundaries(self):
        """Import real boundary modules in a fresh process without loading Docker."""
        code = """
import sys
import laomedo.work_graph.stage_worker
import laomedo.host.credentials.git_credential_helper
import laomedo.agents.providers.codex.preflight.service
assert not any(n == 'py_docker' or n.startswith('py_docker.') for n in sys.modules)
assert 'docker' not in sys.modules
"""
        result = subprocess.run(
            [sys.executable, "-c", code], check=False, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_private_environment_is_not_serialized(self):
        """Prevent host environment values reaching logs or public records."""
        selection = DockerSelection(
            image_id="sha256:" + "a" * 64, environment={"PRIVATE": "sensitive"}
        )
        self.assertNotIn("sensitive", repr(selection))
        self.assertEqual(selection.model_dump(), {"image_id": selection.image_id})

    def test_every_new_preflight_error_producer_has_descriptive_catalogue_coverage(
        self,
    ):
        """Require catalogue coverage for every literal public code in this feature."""
        catalogue = json.loads(
            ROOT.joinpath(
                "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
        source = ROOT.joinpath(
            "src/laomedo/agents/providers/codex/preflight/service.py"
        )
        codes = set()
        for node in ast.walk(ast.parse(source.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "RunnerError"
            ):
                self.assertIsInstance(node.args[0], ast.Constant)
                codes.add(node.args[0].value)
        self.assertEqual(
            codes,
            {
                "docker_image_digest_changed",
                "unsupported_codex_cli_version",
                "runner_docker_check_unconfirmed",
                "container_termination_unverified",
            },
        )
        for code in codes:
            for field in ("title", "description", "recovery"):
                self.assertTrue(catalogue[code][field].strip())


@unittest.skipUnless(
    importlib.util.find_spec("py_docker"), "Install the optional runner dependency"
)
class PreflightControls(unittest.TestCase):
    """Inject only internal control faults, never a demonstration provider."""

    def setUp(self):
        """Create private temporary state and canonical runtime ownership records."""
        from py_docker.containers.models import ContainerIdentity, ContainerReservation
        from py_docker.streams.models import Frame

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.preflight = CodexPreflight(Path(self.temp.name))
        self.expected = "sha256:" + "a" * 64
        self.receipt = ContainerReservation(
            name="private-probe", labels={"py_docker.owner": "private-token"}
        )
        self.identity = ContainerIdentity(
            id="b" * 64, name=self.receipt.name, labels=self.receipt.labels
        )
        self.client = MagicMock()
        self.client.containers.reserve.return_value = self.receipt
        self.client.containers.create.return_value = self.identity
        self.client.containers.reconcile.return_value = self.identity
        self.client.sdk.containers.get.return_value.wait.return_value = {
            "StatusCode": 0
        }
        self.stream = self.client.execution.attach.return_value.__enter__.return_value
        self.stream.read_frame.side_effect = [
            Frame(channel="stderr", data=b"ignored"),
            Frame(channel="stdout", data=b"codex-cli 0.159.2\n"),
            None,
        ]

    def test_valid_version_attaches_before_start_and_cleans_exact_identity(self):
        """Check command policy, ordering and deterministic ownership cleanup."""
        self.preflight._probe(self.client, "local-image", self.expected)
        self.client.images.resolve.assert_called_once_with(
            "local-image", expected_id=self.expected
        )
        spec = self.client.containers.reserve.call_args.args[0]
        self.assertEqual(spec.image, self.expected)
        self.assertEqual(spec.user, "10001:10001")
        self.assertEqual(spec.network_mode, "none")
        self.assertTrue(spec.read_only)
        self.assertFalse(spec.volumes)
        calls = [str(call) for call in self.client.mock_calls]
        self.assertLess(
            next(
                i for i, c in enumerate(calls) if c.startswith("call.execution.attach(")
            ),
            next(
                i for i, c in enumerate(calls) if c.startswith("call.containers.start(")
            ),
        )
        self.client.containers.remove.assert_called_once_with(self.identity, force=True)
        self.assertFalse(self.preflight.receipt_path.exists())

    def test_image_mismatch_never_creates_a_probe(self):
        """Retain the stable pin code and discard external exception context."""
        from py_docker.errors import OwnershipConflictError

        self.client.images.resolve.side_effect = OwnershipConflictError(
            "private diagnostic"
        )
        with self.assertRaisesRegex(
            RunnerError, "^docker_image_digest_changed$"
        ) as caught:
            self.preflight._probe(self.client, "local-image", self.expected)
        self.assertTrue(caught.exception.__suppress_context__)
        self.client.containers.create.assert_not_called()

    def test_invalid_utf8_is_a_version_error_after_cleanup(self):
        """Do not leak undecodable native output into the public error."""
        from py_docker.streams.models import Frame

        self.stream.read_frame.side_effect = [
            Frame(channel="stdout", data=b"\xff"),
            None,
        ]
        with self.assertRaisesRegex(RunnerError, "^unsupported_codex_cli_version$"):
            self.preflight._probe(self.client, "local-image", self.expected)
        self.client.containers.remove.assert_called_once()

    def test_cleanup_failure_wins_and_retains_private_receipt(self):
        """Unverified resources take precedence over a failed version check."""
        from py_docker.errors import DockerOperationError

        self.client.sdk.containers.get.return_value.wait.return_value = {
            "StatusCode": 7
        }
        self.client.containers.remove.side_effect = DockerOperationError(
            "private error"
        )
        with self.assertRaisesRegex(RunnerError, "^container_termination_unverified$"):
            self.preflight._probe(self.client, "local-image", self.expected)
        self.assertTrue(self.preflight.receipt_path.exists())

    def test_absence_after_uncertain_create_does_not_authorize_another_probe(self):
        """A delayed daemon create cannot be ruled out by immediate absence."""
        from py_docker.errors import CreationUnconfirmedError

        self.client.containers.create.side_effect = CreationUnconfirmedError(
            "create", self.receipt
        )
        self.client.containers.reconcile.return_value = None
        with self.assertRaisesRegex(RunnerError, "container_termination_unverified"):
            self.preflight._probe(self.client, "local-image", self.expected)
        self.assertTrue(self.preflight.receipt_path.exists())
        with self.assertRaisesRegex(RunnerError, "container_termination_unverified"):
            self.preflight._recover(self.client)
        self.client.containers.remove.assert_not_called()
        self.assertEqual(self.client.containers.create.call_count, 1)

    def test_retained_receipt_recovers_only_observed_owned_container(self):
        """Reconcile and remove the owned ID before clearing the private record."""
        self.preflight._save(self.receipt)
        self.preflight._recover(self.client)
        self.client.containers.reconcile.assert_called_once_with(self.receipt)
        self.client.containers.remove.assert_called_once_with(self.identity, force=True)
        self.assertFalse(self.preflight.receipt_path.exists())

    def test_selected_endpoint_pins_cli_snapshot_and_ignores_library_env_overrides(
        self,
    ):
        """Prevent SDK and subsequent CLI calls selecting different engines."""
        self.client.connection.endpoint = "npipe:////./pipe/docker_engine"
        self.client.__enter__.return_value = self.client
        snapshot = {
            "DOCKER_CONTEXT": "desktop-linux",
            "PY_DOCKER_ENDPOINT": "tcp://untrusted:2375",
            "PATH": "host-path",
        }
        with (
            patch(
                "py_docker.connection.settings.ConnectionSettings.environment_snapshot",
                return_value=snapshot,
            ),
            patch("py_docker.Client", return_value=self.client) as factory,
            patch.object(self.preflight, "_probe"),
        ):
            selected = self.preflight.check("image", self.expected)
        self.assertEqual(
            selected.environment["DOCKER_HOST"], self.client.connection.endpoint
        )
        self.assertNotIn("DOCKER_CONTEXT", selected.environment)
        self.assertEqual(factory.call_args.kwargs["environment"], snapshot)
        self.assertIsNone(factory.call_args.kwargs["settings"].endpoint)
        self.assertEqual(factory.call_args.kwargs["settings"].timeout_seconds, 15)
