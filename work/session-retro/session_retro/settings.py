"""Explicit local resource limits; no profile or credential configuration."""

import hashlib
import json
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PARSER_VERSION = "codex-retro-1"


class Settings(BaseSettings):
    """Inject RETRO_ environment values at command invocation, never import time."""

    model_config = SettingsConfigDict(env_prefix="RETRO_", extra="forbid")
    private_root: Path | None = Field(
        default=None,
        description="Explicit private output root; all generated files must remain beneath it",
    )
    chunk_bytes: int = Field(
        default=1024 * 1024,
        ge=1024,
        le=8 * 1024 * 1024,
        description="Fixed byte scan buffer",
    )
    max_record_bytes: int = Field(
        default=8 * 1024 * 1024,
        ge=1024,
        le=32 * 1024 * 1024,
        description="Largest JSON record decoded in memory",
    )
    batch_records: int = Field(
        default=200,
        ge=1,
        le=2000,
        description="Maximum records in one committed SQLite batch",
    )
    search_characters: int = Field(
        default=4096,
        ge=128,
        le=32768,
        description="Stored extracted characters per source record",
    )
    read_characters: int = Field(
        default=16000,
        ge=128,
        le=65536,
        description="Maximum extracted characters per read page",
    )
    page_records: int = Field(
        default=50, ge=1, le=200, description="Maximum metadata/search rows per command"
    )

    def digest(self) -> str:
        """Bind resumability to limits affecting record interpretation and search."""
        values = {
            "max_record_bytes": self.max_record_bytes,
            "search_characters": self.search_characters,
        }
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
