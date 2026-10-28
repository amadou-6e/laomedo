"""Constants shared by the owning feature; mutable state has one owner."""

from __future__ import annotations

import re

MAX_BUNDLE_BYTES = 4 * 1024 * 1024


MAX_RECORD_BYTES = 256 * 1024


HANDOFF_NAME = ".laomedo-handoff.bundle"


_IDENTITY = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")


_SHA = re.compile(r"[0-9a-f]{40}\Z")


_BRANCH = re.compile(r"[A-Za-z0-9._/-]+\Z")


_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
