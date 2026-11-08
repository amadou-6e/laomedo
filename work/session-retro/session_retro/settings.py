"""Explicit local resource limits; no profile or credential configuration."""

import hashlib
import json
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PARSER_VERSION = "codex-retro-2"

# Stable local failure explanations, not user-editable runtime configuration.
ERROR_MESSAGES = {
    "index_locator_integrity_failed": "Indexed record spans no longer reconcile with the committed source prefix.",
    "invalid_source_boundary": "The requested finite boundary is outside the source or precedes its identity record.",
    "index_boundary_mismatch": "An explicit boundary differs from this index; use a new index or an intentional extension.",
    "invalid_session_metadata": "The first source record is not supported Codex session metadata.",
    "session_identity_mismatch": "The selected file does not identify the expected session.",
    "source_replaced": "The file at the selected path has been replaced since indexing.",
    "source_truncated": "The source is shorter than the captured indexing boundary.",
    "source_prefix_changed": "Previously indexed source bytes changed; existing evidence is stale.",
    "source_record_changed": "The requested source record no longer matches its stored hash.",
    "source_is_database": "The output database must be a different file from the session source.",
    "record_requires_bounded_large_payload_decoder": "This record exceeds the safe parsing limit and remains an explicit coverage gap.",
    "record_outside_indexed_prefix": "The requested record lies beyond the admitted indexed prefix.",
    "private_root_required": "Select a private output root before creating or reading derived evidence.",
    "database_outside_private_root": "The selected database is outside the configured private output root.",
    "database_not_owned": "The selected database belongs to another application and was refused.",
    "index_missing": "The selected index does not exist; create it from the intended source first.",
    "index_not_initialized": "The database has no admitted source checkpoint yet.",
    "index_source_mismatch": "This index belongs to a different source or session.",
    "index_settings_changed": "Parser or interpretation settings differ from the existing index.",
    "invalid_record_page": "The requested source line or text-page position is invalid.",
    "report_outside_private_root": "Reports must remain inside the configured private output root.",
    "invalid_stop_after": "An interruption checkpoint must stop after at least one record.",
    "filesystem_or_settings_failed": "A filesystem, index-storage or settings operation could not complete.",
}


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
