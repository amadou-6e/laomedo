"""Constants shared by the owning feature; mutable state has one owner."""

from __future__ import annotations

import re

_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
