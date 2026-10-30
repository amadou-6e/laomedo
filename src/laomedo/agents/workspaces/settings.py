"""Feature settings and fixed protocol values; mutable state has one owner."""

from __future__ import annotations

import re

_SHA = re.compile(rb"[0-9a-f]{40}\Z")


MAX_GIT_WORKSPACE_SNAPSHOT_BYTES = 64 * 1024 * 1024
MAX_GIT_WORKSPACE_SNAPSHOT_ENTRIES = 10000
