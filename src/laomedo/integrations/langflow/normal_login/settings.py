"""Explicit location policy; no credential values."""

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class NormalLoginSettings(BaseSettings):
    """Read the task-owned runtime path without dotenv or secret files."""

    model_config = SettingsConfigDict(
        env_file=None,
        secrets_dir=None,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )
    runtime_root: Path = Field(
        validation_alias="LAOMEDO_NORMAL_LOGIN_RUNTIME",
        description="Absolute isolated runtime root.",
    )
