"""Per-profile native API runtime values and its deployment settings."""

from pathlib import Path
from uuid import UUID

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from laomedo.integrations.langflow.execution.settings import BaseDockerRuntimeSettings
from laomedo.integrations.langflow.execution.utils import private_state_path

NATIVE_PROFILE_PORT = 7860
NATIVE_PROFILE_PROBE_BYTES = 65536
NATIVE_PROFILE_STATE_PATH = "/var/lib/laomedo/graphs"
NATIVE_PROFILE_DEPLOYMENT_LABEL = "laomedo.graph.deployment"
NATIVE_PROFILE_OWNER_LABEL = "laomedo.graph.owner"


class NativeProfileSettings(BaseSettings):
    """Trusted bootstrap for graph metadata, never broker profile authentication."""

    model_config = SettingsConfigDict(
        frozen=True,
        extra="forbid",
        env_file=None,
        secrets_dir=None,
        hide_input_in_errors=True,
    )
    owner_id: UUID = Field(
        description="Broker-selected profile's operational identity inside this container only."
    )
    state_root: Path = Field(
        description="Container-owned operational store, separate from broker identity and credentials."
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
        """Browser parameters, environment and dotenv do not select an owner."""
        return (init_settings,)

    @field_validator("state_root")
    @classmethod
    def absolute_store(cls, value):
        """Reject relative paths or indirection in the container-owned store."""
        return private_state_path(value)


class NativeProfileDeploymentSettings(BaseDockerRuntimeSettings):
    """Explicit local native API deployment, separate from job authority.

    `image_id` is the native API runtime image digest; the limits apply to each
    profile's long-lived API container.
    """

    deployment_id: UUID = Field(
        description="Durable host-owned namespace; separate installations never share profile volumes."
    )
    memory_mib: int = Field(
        default=2048,
        strict=True,
        gt=0,
        description="Native API container memory limit in MiB.",
    )
    pids: int = Field(
        default=256, strict=True, gt=0, description="Native API process count limit."
    )
    startup_timeout_seconds: float = Field(
        default=90.0,
        strict=True,
        gt=0,
        allow_inf_nan=False,
        description="Native database/API readiness timeout, not a model-run budget.",
    )
