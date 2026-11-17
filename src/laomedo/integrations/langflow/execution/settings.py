"""Fixed private-pipe protocol values, not model-turn or verification budgets."""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

GRAPH_WORKER_PREFIX = b"LAOMEDO_GRAPH_V1 "
GRAPH_WORKER_MESSAGE_BYTES = 16 * 1024 * 1024


class GraphWorkerSettings(BaseSettings):
    """Explicit local container deployment, never supplied by a graph or worker."""

    model_config = SettingsConfigDict(
        frozen=True,
        extra="forbid",
        env_file=None,
        secrets_dir=None,
        hide_input_in_errors=True,
    )
    image_id: str = Field(
        pattern=r"^sha256:[0-9a-f]{64}$",
        description="Verified final local worker image digest, never a mutable tag.",
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
        description="Per-job container memory limit in MiB.",
    )
    cpus: float = Field(
        default=2.0,
        strict=True,
        gt=0,
        allow_inf_nan=False,
        description="Per-job CPU resource allocation.",
    )
    pids: int = Field(
        default=128, strict=True, gt=0, description="Per-job process count limit."
    )
    temporary_mib: int = Field(
        default=256,
        strict=True,
        gt=0,
        description="Job-owned /tmp memory filesystem size in MiB.",
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
        """Only admitted host arguments configure worker isolation."""
        return (init_settings,)

    @field_validator("lease_state")
    @classmethod
    def private_absolute_state(cls, value):
        """Refuse repository-owned supervisor state or filesystem indirection."""
        if not value.is_absolute():
            raise ValueError("graph_worker_state_invalid")
        if any(
            (path / ".git").exists() or path.is_symlink() or path.is_junction()
            for path in (value, *value.parents)
        ):
            raise ValueError("graph_worker_state_invalid")
        return value
