"""Feature settings and fixed protocol values; mutable state has one owner."""

from __future__ import annotations

import re

_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


_SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")
