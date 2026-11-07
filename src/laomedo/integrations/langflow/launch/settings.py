"""Validate the caller-selected paths for a local Langflow installation."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Hold explicit launch arguments without loading dotenv or secret files."""

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=None,
        secrets_dir=None,
        enable_decoding=False,
        frozen=True,
        hide_input_in_errors=True,
    )

    runner_config: Path = Field(
        description="Private host-owned runner service JSON file."
    )
    frontend: Path = Field(description="Built matching Langflow frontend directory.")
    components: Path = Field(description="This installation's custom component root.")
    state: Path = Field(description="Persistent Langflow state directory outside Git.")
    port: int = Field(
        default=7860, ge=1, le=65535, description="Loopback app HTTP port."
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """Use CLI arguments only; unrelated app environment cannot retarget paths."""
        return (init_settings,)

    def validate_paths(self) -> None:
        """Reject incomplete installations and runtime state inside Git before launch.

        Raises ValueError for missing assets, unsafe state, or a missing host file.
        No files or services are created by this check.
        """
        if not self.runner_config.is_file():
            raise ValueError("The local runner configuration file does not exist.")
        if not (self.frontend / "index.html").is_file():
            raise ValueError(
                "Build the matching Langflow frontend before starting the app."
            )
        if not (self.components / "laomedo" / "codex_agent.py").is_file():
            raise ValueError("Select this installation's components directory.")
        for path in (self.state.resolve(), self.runner_config.resolve().parent):
            if any((parent / ".git").exists() for parent in (path, *path.parents)):
                raise ValueError("Keep app state and runner configuration outside Git.")
