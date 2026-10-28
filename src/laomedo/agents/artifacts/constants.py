"""Constants shared by the owning feature; mutable state has one owner."""

from __future__ import annotations

import re

HASH = re.compile(r"sha256:[0-9a-f]{64}")
