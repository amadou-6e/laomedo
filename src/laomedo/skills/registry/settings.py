"""Feature settings and fixed protocol values; mutable state has one owner."""

from __future__ import annotations

import re

NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


HASH = re.compile(r"^sha256:[0-9a-f]{64}$")

ASSET_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf"})


MAX_FILES = 128


MAX_DIRECTORIES = 128


MAX_DEPTH = 16


MAX_FILE_BYTES = 512 * 1024


MAX_BUNDLE_BYTES = 4 * 1024 * 1024
