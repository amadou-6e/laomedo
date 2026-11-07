"""App configuration controls; these do not establish real runner acceptance."""

import json
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from laomedo.integrations.langflow.launch.service import AppLauncher
from laomedo.integrations.langflow.launch.settings import Settings


class AppLaunchTests(unittest.TestCase):
    """Protect the same-config recovery, token and new-node endpoint binding."""

    def setUp(self):
        """Create a credential-free installation description outside Git."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        frontend = self.root / "frontend"
        frontend.mkdir()
        (frontend / "index.html").write_text("frontend")
        components = self.root / "components"
        (components / "laomedo").mkdir(parents=True)
        (components / "laomedo/codex_agent.py").write_text("component")
        self.config = {
            "provider": "codex",
            "state": str(self.root / "runner"),
            "skill_store": str(self.root / "registry"),
            "source": str(self.root / "source"),
            "port": 19876,
            "lease_service": str(self.root / "lease"),
        }
        (self.root / "source").mkdir()
        self.path = self.root / "runner.json"
        self.path.write_text(json.dumps(self.config))
        self.settings = Settings(
            runner_config=self.path,
            frontend=frontend,
            components=components,
            state=self.root / "app",
        )

    def test_one_config_binds_recovery_token_registry_and_new_node_endpoint(self):
        """Environment is derived without reading a token or starting any process."""
        with patch("subprocess.Popen") as spawn:
            environment = AppLauncher(self.settings).environment()
        spawn.assert_not_called()
        self.assertEqual(environment["LAOMEDO_RUNNER_SERVICE_FILE"], str(self.path))
        self.assertEqual(
            Path(environment["LAOMEDO_RUNNER_TOKEN_FILE"]),
            self.root / "runner/api-token",
        )
        self.assertFalse((self.root / "runner/api-token").exists())
        self.assertEqual(
            environment["LAOMEDO_CODEX_RUNNER_URL"], "http://127.0.0.1:19876"
        )
        self.assertEqual(environment["LAOMEDO_SKILL_STORE"], self.config["skill_store"])
        self.assertIn("/app/flow.db", environment["LANGFLOW_DATABASE_URL"])

    def test_missing_host_config_or_frontend_refuses_launch(self):
        """An incomplete installation never reaches uvicorn or exposes auto-login."""
        for field, value in (
            ("runner_config", self.root / "missing.json"),
            ("frontend", self.root / "unbuilt"),
            ("components", self.root / "missing-components"),
        ):
            with self.subTest(field=field):
                settings = self.settings.model_copy(update={field: value})
                with self.assertRaises(ValueError):
                    AppLauncher(settings).environment()

    def test_git_runtime_state_is_rejected_without_writing_files(self):
        """Saved graphs and signing keys must remain outside any Git checkout."""
        (self.root / ".git").mkdir()
        with self.assertRaisesRegex(ValueError, "outside Git"):
            AppLauncher(self.settings).environment()
        self.assertFalse(self.settings.state.exists())

    def test_malformed_runner_config_is_reported_without_its_contents(self):
        """Invalid JSON is a safe setup error, not a raw credential-bearing dump."""
        self.path.write_text("private malformed content")
        with self.assertRaisesRegex(
            ValueError, "^The local runner configuration is invalid.$"
        ):
            AppLauncher(self.settings).environment()

    def test_unrelated_environment_cannot_override_explicit_launch_arguments(self):
        """Paths and ports come from the trusted command, not ambient overrides."""
        with patch.dict("os.environ", {"LAOMEDO_APP_PORT": "1234"}):
            settings = Settings(**self.settings.model_dump())
        self.assertEqual(settings.port, 7860)

    def test_missing_supervisor_binding_is_a_setup_error(self):
        """A recoverable API must also have its normal run supervision binding."""
        del self.config["lease_service"]
        self.path.write_text(json.dumps(self.config))
        with self.assertRaisesRegex(ValueError, "independent Codex lease service"):
            AppLauncher(self.settings).environment()

    def test_port_collision_refuses_app_startup(self):
        """An app cannot occupy the managed runner endpoint even while it is offline."""
        settings = self.settings.model_copy(update={"port": self.config["port"]})
        with self.assertRaisesRegex(ValueError, "different ports"):
            AppLauncher(settings).environment()

    def test_activity_defaults_are_installation_scoped_and_existing_path_is_explicit(
        self,
    ):
        """Sibling app directories never silently share a new activity database."""
        first = AppLauncher(self.settings).environment()
        second = AppLauncher(
            self.settings.model_copy(update={"state": self.root / "second-app"})
        ).environment()
        self.assertEqual(
            Path(first["LAOMEDO_AGENT_ACTIVITY_DB"]), self.root / "app/activity.db"
        )
        self.assertNotEqual(
            first["LAOMEDO_AGENT_ACTIVITY_DB"], second["LAOMEDO_AGENT_ACTIVITY_DB"]
        )
        existing = self.root / "existing-activity.db"
        retained = AppLauncher(
            self.settings.model_copy(update={"activity_db": existing})
        ).environment()
        self.assertEqual(Path(retained["LAOMEDO_AGENT_ACTIVITY_DB"]), existing)

    def test_new_component_reads_the_launch_endpoint_before_langflow_loads_it(self):
        """Actual component definition uses the derived host URL at import time."""
        path = Path(__file__).resolve().parents[2] / "components/laomedo/codex_agent.py"
        spec = importlib.util.spec_from_file_location("launch_codex_component", path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict("os.environ", AppLauncher(self.settings).environment()):
            spec.loader.exec_module(module)
        fields = {field.name: field for field in module.LaomedoCodexAgent.inputs}
        self.assertEqual(fields["runner_url"].value, "http://127.0.0.1:19876")
