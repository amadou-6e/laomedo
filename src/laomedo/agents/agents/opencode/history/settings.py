"""Bounded, metadata-only native history reads for the pinned OpenCode CLI."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DATABASE_FILE = "opencode.db"
MAX_EXPORT_BYTES = 8 * 1024 * 1024
MAX_SESSIONS = 32
EXPORT_SECONDS = 30


class Settings(BaseSettings):
    """Bound host-selected memory use without reading dotenv or secret stores."""

    model_config = SettingsConfigDict(
        env_file=None,
        secrets_dir=None,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
        case_sensitive=True,
        enable_decoding=False,
    )
    max_database_bytes: int = Field(
        default=128 * 1024 * 1024,
        gt=0,
        le=512 * 1024 * 1024,
        validation_alias="LAOMEDO_OPENCODE_HISTORY_MAX_DATABASE_BYTES",
        description="Host-only byte ceiling for a consistent native history snapshot, up to 512 MiB.",
    )
    export_batch_seconds: int = Field(
        default=120,
        ge=45,
        le=600,
        validation_alias="LAOMEDO_OPENCODE_HISTORY_EXPORT_SECONDS",
        description="Host-only whole-tree deadline, including native CLI startup and exact Docker cleanup; each export remains limited to 30 seconds.",
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
        return init_settings, env_settings
