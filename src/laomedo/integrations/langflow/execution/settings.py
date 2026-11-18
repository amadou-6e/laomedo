"""Shared local-Docker control bounds and deployment settings for isolated runtimes."""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from laomedo.integrations.langflow.execution.utils import private_state_path

DOCKER_CONTROL_OUTPUT_BYTES = 1024 * 1024
DOCKER_CONTROL_CHUNK_BYTES = 65536


class BaseDockerRuntimeSettings(BaseSettings):
    """Explicit local container deployment shared by the worker and profile runtimes.

    Only admitted host arguments configure isolation; graphs, workers, the
    environment and dotenv files never do. Each runtime subclass documents its
    own defaults and adds its own fields.
    """

    model_config = SettingsConfigDict(
        frozen=True,
        extra="forbid",
        env_file=None,
        secrets_dir=None,
        hide_input_in_errors=True,
    )
    image_id: str = Field(
        pattern=r"^sha256:[0-9a-f]{64}$",
        description="Verified final local image digest for this runtime, never a mutable tag.",
    )
    lease_state: Path = Field(
        description="Private state of an independently started matching Docker lease service."
    )
    docker_context: str = Field(
        default="desktop-linux",
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$",
        description="Explicit local Docker context; remote endpoints are refused.",
    )
    memory_mib: int = Field(
        default=1024,
        strict=True,
        gt=0,
        description="Container memory limit in MiB.",
    )
    cpus: float = Field(
        default=2.0,
        strict=True,
        gt=0,
        allow_inf_nan=False,
        description="Container CPU resource allocation.",
    )
    pids: int = Field(
        default=128, strict=True, gt=0, description="Container process count limit."
    )
    temporary_mib: int = Field(
        default=256,
        strict=True,
        gt=0,
        description="Container-owned /tmp memory filesystem size in MiB.",
    )
    control_timeout_seconds: float = Field(
        default=15.0,
        strict=True,
        gt=0,
        allow_inf_nan=False,
        description="Docker metadata/control command timeout, separate from execution policy.",
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
        """Only admitted host arguments configure runtime isolation."""
        return (init_settings,)

    @field_validator("lease_state")
    @classmethod
    def private_absolute_state(cls, value):
        """Refuse repository-owned supervisor state or filesystem indirection."""
        return private_state_path(value)
