"""Redact known credential fields before persisting provider observations."""

import re

from laomedo.agents.activity.redaction.settings import SECRET_KEYS


def sanitized(value):
    """Return a JSON-shaped copy with credential keys and bearer values removed.

    This removes recognized credentials; launch-specific capability secrets still
    require the owning runner's exact-value redactor before reaching this layer.
    """
    if isinstance(value, dict):
        return {
            key: "[redacted]" if key.lower() in SECRET_KEYS else sanitized(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitized(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/-]+", "Bearer [redacted]", value)
    return value
