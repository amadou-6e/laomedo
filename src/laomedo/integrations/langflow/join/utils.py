"""Implementation owned by integrations / langflow / join / utils."""

from __future__ import annotations

from hashlib import sha256
from uuid import UUID
import json
import laomedo.agents.workflow.errors as _workflow_errors


def _digest(value):
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + sha256(encoded).hexdigest()


def _uuid(value, category):
    try:
        canonical = str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        raise _workflow_errors.LaunchError(category) from None
    if canonical != value:
        raise _workflow_errors.LaunchError(category)
    return canonical
