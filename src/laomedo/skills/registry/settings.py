"""Feature settings and fixed protocol values; mutable state has one owner."""

from __future__ import annotations

import re

NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
