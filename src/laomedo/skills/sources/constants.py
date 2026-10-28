"""Constants shared by the owning feature; mutable state has one owner."""

from __future__ import annotations

SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv"}


SECRET = {"auth.json", "credentials.json", "credentials", ".env", ".netrc"}


MAX_ENTRIES = 4096
