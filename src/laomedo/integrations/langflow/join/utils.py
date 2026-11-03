"""Implementation owned by integrations / langflow / join / utils."""

from __future__ import annotations

from hashlib import sha256
from uuid import UUID
import json
from laomedo.work_graph.runs.errors import LaunchError


def _digest(value):
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + sha256(encoded).hexdigest()


def _uuid(value, category):
    try:
        canonical = str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        raise LaunchError(category) from None
    if canonical != value:
        raise LaunchError(category)
    return canonical
