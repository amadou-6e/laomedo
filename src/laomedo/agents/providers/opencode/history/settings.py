"""Bounded, metadata-only native history reads for the pinned OpenCode CLI."""

DATABASE_FILE = "opencode.db"
MAX_DATABASE_BYTES = 128 * 1024 * 1024
MAX_EXPORT_BYTES = 8 * 1024 * 1024
MAX_SESSIONS = 32
EXPORT_SECONDS = 30
EXPORT_BATCH_SECONDS = 45
