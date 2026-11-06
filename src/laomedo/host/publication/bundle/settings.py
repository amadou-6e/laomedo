"""Feature settings and fixed protocol values; mutable state has one owner."""

from __future__ import annotations

from pathlib import Path
from laomedo._paths import package_root
import re

_IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")


_SHA = re.compile(r"[0-9a-f]{64}\Z")


_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


_OBJECT_ID = re.compile(rb"[0-9a-f]{40}\Z")


SCRIPT = package_root() / "host" / "publication" / "resources" / "bundle_stage.sh"


SCRIPT_LF_SHA256 = "5a7c32be96594c5a5ee3341f2870e85d83673860ec515996928e6badfb4368f5"


PINNED_IMAGE_ID = (
    "sha256:eceda79a349c46a8afd6fb271e92b979f872ca67cbdf228fde6dee0856481e78"
)


MEMORY_BYTES = 128 * 1024 * 1024


MAX_OUTPUT_BYTES = 32 * 1024 * 1024
