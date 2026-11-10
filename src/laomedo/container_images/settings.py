"""Budgets for image installation, separate from agent execution."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ImageBuildSettings(BaseSettings):
    """Load installation budgets at acquisition time, not at module import."""

    model_config = SettingsConfigDict(env_prefix="LAOMEDO_IMAGE_", extra="ignore")
    build_seconds: float = Field(
        default=900, gt=0, le=7200, description="Build and lock-wait budget."
    )
    verify_seconds: float = Field(
        default=30, gt=0, le=300, description="Zero-turn version check budget."
    )
    context_bytes: int = Field(
        default=32 * 1024 * 1024,
        gt=0,
        description="Maximum registered build context bytes.",
    )
