"""Internal preflight controls; real Docker/agent acceptance is recorded separately."""

import ast
import builtins
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

    def test_missing_optional_runtime_has_an_actionable_safe_startup_log(self):
        """The manual and managed constructor path names the missing install extra."""
        original = builtins.__import__

        def without_runtime(name, *args, **kwargs):
            """Inject only the missing optional dependency for this internal control."""
            if name == "docker.errors":
                raise ImportError("external private diagnostic")
            return original(name, *args, **kwargs)

        with (
            tempfile.TemporaryDirectory() as directory,
            patch("builtins.__import__", side_effect=without_runtime),
            self.assertLogs(
                "laomedo.agents.providers.codex.preflight.service", level="WARNING"
            ) as logs,
            self.assertRaisesRegex(RunnerError, "^runner_docker_check_unconfirmed$"),
        ):
            CodexPreflight(Path(directory)).check("image", "sha256:" + "a" * 64)
        self.assertIn(".[runner]", logs.output[0])
        self.assertNotIn("external private diagnostic", logs.output[0])

    def test_current_security_policy_retains_canonical_checkout_bytes(self):
        """Keep the moved hashed seccomp policy under its LF checkout rule."""
        attributes = ROOT.joinpath(".gitattributes").read_text()
        self.assertIn(
            "src/laomedo/agents/providers/codex/resources/codex-seccomp.json text eol=lf",
            attributes,
        )

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
    """Verify Codex policy and delegation, not the library's lifecycle internals."""

    def setUp(self):
        """Allocate private state and inject the actual library service boundary."""
        from py_docker.execution.models import CommandResult

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.preflight = CodexPreflight(Path(self.temp.name))
        self.expected = "sha256:" + "a" * 64
        self.client = MagicMock()
        self.client.__enter__.return_value = self.client
        self.client.jobs.run.return_value = CommandResult(
            exit_code=0, stdout=b"codex-cli 0.159.2\n", stderr=b""
        )

    def test_version_policy_delegates_the_hardened_job_to_the_library(self):
        """Keep application security choices explicit at the reusable job boundary."""
        self.preflight._probe(self.client, "local-image", self.expected)
        self.client.images.resolve.assert_called_once_with(
            "local-image", expected_id=self.expected
        )
        job = self.client.jobs.run.call_args.args[0]
        self.assertEqual(job.spec.image, self.expected)
        self.assertEqual(job.spec.user, "10001:10001")
        self.assertEqual(job.spec.network_mode, "none")
        self.assertEqual(job.spec.cap_drop, ["ALL"])
        self.assertEqual(job.spec.security_opt, ["no-new-privileges:true"])
        self.assertTrue(job.spec.read_only)
        self.assertFalse(job.spec.volumes)
        self.assertEqual(job.receipt_path, self.preflight.receipt_path)
        self.assertEqual(job.limits.max_bytes, 65536)
        self.client.containers.create.assert_not_called()
        self.client.execution.attach.assert_not_called()

    def test_image_mismatch_never_dispatches_a_job(self):
        """Keep the stable pin refusal without generic lifecycle work in Laomedo."""
        from py_docker.errors import OwnershipConflictError

        self.client.images.resolve.side_effect = OwnershipConflictError("safe phase")
        with self.assertRaisesRegex(RunnerError, "^docker_image_digest_changed$"):
            self.preflight._probe(self.client, "image", self.expected)
        self.client.jobs.run.assert_not_called()

    def test_wrong_version_nonzero_exit_and_invalid_utf8_are_version_failures(self):
        """Interpret only a completed library result against the pinned Codex version."""
        from py_docker.execution.models import CommandResult

        for output, status in (
            (b"codex-cli unexpected", 0),
            (b"codex-cli 0.159.2", 7),
            (b"\xff", 0),
        ):
            with self.subTest(output=output, status=status):
                self.client.jobs.run.return_value = CommandResult(
                    exit_code=status, stdout=output, stderr=b"private ignored output"
                )
                with self.assertRaisesRegex(
                    RunnerError, "^unsupported_codex_cli_version$"
                ):
                    self.preflight._probe(self.client, "image", self.expected)

    def test_cleanup_uncertainty_maps_to_existing_error_before_policy_or_dispatch(self):
        """Startup recovery is explicit and blocks another job when it is unconfirmed."""
        from py_docker.errors import CleanupUnconfirmedError

        self.client.jobs.recover.side_effect = CleanupUnconfirmedError(
            "recover owned job"
        )
        with (
            patch("py_docker.Client", return_value=self.client),
            self.assertRaisesRegex(RunnerError, "^container_termination_unverified$") as caught,
        ):
            self.preflight.check("image", self.expected)
        self.assertTrue(caught.exception.__suppress_context__)
        self.client.images.resolve.assert_not_called()
        self.client.jobs.run.assert_not_called()

    def test_library_failure_stays_safe_and_does_not_claim_missing_image(self):
        """Preserve uncertainty rather than inferring a cause from an SDK failure."""
        from py_docker.errors import DockerOperationError

        self.client.jobs.run.side_effect = DockerOperationError("read owned job")
        with (
            patch("py_docker.Client", return_value=self.client),
            self.assertRaisesRegex(RunnerError, "^runner_docker_check_unconfirmed$"),
        ):
            self.preflight.check("image", self.expected)

    def test_selected_endpoint_pins_cli_snapshot_and_ignores_library_env_overrides(
        self,
    ):
        """Keep reusable jobs and subsequent CLI calls on the selected local engine."""
        self.client.connection.endpoint = "npipe:////./pipe/docker_engine"
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
        ):
            selected = self.preflight.check("image", self.expected)
        self.assertEqual(
            selected.environment["DOCKER_HOST"], self.client.connection.endpoint
        )
        self.assertNotIn("DOCKER_CONTEXT", selected.environment)
        self.assertIsNone(factory.call_args.kwargs["settings"].endpoint)
        self.client.jobs.recover.assert_called_once_with(self.preflight.receipt_path)

    def test_generic_lifecycle_implementation_does_not_return_to_the_policy_adapter(
        self,
    ):
        """Guard the outsourcing boundary instead of retaining duplicate implementations."""
        methods = set(CodexPreflight.__dict__)
        self.assertFalse(methods & {"_save", "_recover", "_cleanup"})
