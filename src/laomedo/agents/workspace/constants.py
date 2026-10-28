"""Constants shared by the owning feature; mutable state has one owner."""

from __future__ import annotations

import re

_SHA = re.compile(rb"[0-9a-f]{40}\Z")


GIT_COMMAND_TIMEOUT_SECONDS = 30
