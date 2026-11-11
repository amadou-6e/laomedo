"""Bind app inspection and recovery to the same trusted local runner."""

import os
from pathlib import Path

from laomedo.host.runner.service import RunnerService
from laomedo.integrations.langflow.launch.settings import Settings


class AppLauncher:
    """Configure one local app; runner startup remains an explicit recovery action."""

    def __init__(self, settings: Settings):
        """Retain validated caller arguments; construction starts no services."""
        self.settings = settings

    def environment(self) -> dict[str, str]:
        """Derive token, endpoint and registry from the existing host service file.

        Returns process environment updates without reading any token contents.
        Raises ValueError before launch if paths or host configuration are invalid.
        """
        settings = self.settings
        settings.validate_paths()
        try:
            config = RunnerService(settings.runner_config).config()
        except (ValueError, KeyError, OSError) as exc:
            raise ValueError("The local runner configuration is invalid.") from exc
        if config["provider"] != "codex":
            raise ValueError(
                "This app launch command currently requires a Codex runner."
            )
        if "lease_service" not in config:
            raise ValueError(
                "Configure the independent Codex lease service before launch."
            )
        if not Path(config["source"]).is_dir():
            raise ValueError("The configured Codex source directory does not exist.")
        if settings.port == config["port"]:
            raise ValueError("Choose different ports for the app and Codex runner.")
        state = settings.state.resolve()
        environment = {
            "LAOMEDO_RUNNER_SERVICE_FILE": str(settings.runner_config.resolve()),
            "LAOMEDO_RUNNER_TOKEN_FILE": str(Path(config["state"]) / "api-token"),
            "LAOMEDO_SKILL_STORE": config["skill_store"],
            "LAOMEDO_AGENT_ACTIVITY_DB": str(
                settings.activity_db.resolve()
                if settings.activity_db is not None
                else state / "activity.db"
            ),
            "LANGFLOW_CONFIG_DIR": str(state),
            "LFX_CONFIG_DIR": str(state),
            "LANGFLOW_DATABASE_URL": "sqlite:///" + (state / "flow.db").as_posix(),
            "LANGFLOW_FRONTEND_PATH": str(settings.frontend.resolve()),
            "LANGFLOW_COMPONENTS_PATH": str(settings.components.resolve()),
            "LANGFLOW_AUTO_LOGIN": "true",
            "LANGFLOW_DO_NOT_TRACK": "true",
        }
        environment["LAOMEDO_CODEX_RUNNER_URL"] = f"http://127.0.0.1:{config['port']}"
        return environment

    def run(self) -> None:
        """Start only the loopback app with persistent data and managed recovery.

        Imports optional Langflow dependencies only after validation. The app's
        existing recovery action starts the runner; no task or graph is submitted.
        """
        environment = self.environment()
        self.settings.state.mkdir(parents=True, exist_ok=True)
        os.environ.update(environment)
        import laomedo
        import uvicorn

        component_namespace = str(self.settings.components.resolve() / "laomedo")
        if component_namespace not in laomedo.__path__:
            laomedo.__path__.append(component_namespace)
        uvicorn.run(
            "laomedo.integrations.langflow.viewer:create_app",
            factory=True,
            host="127.0.0.1",
            port=self.settings.port,
        )
