"""Normalize safe Claude telemetry attributes."""

from __future__ import annotations

import laomedo.activity.claude.settings as _claude_settings


def safe_attributes(values):
    result = {}
    for pair in values:
        if pair.key not in _claude_settings.SAFE:
            continue
        kind = pair.value.WhichOneof("value")
        if kind in {"string_value", "int_value", "double_value", "bool_value"}:
            value = getattr(pair.value, kind)
            if not isinstance(value, str) or len(value) <= 1024:
                result[pair.key] = value
    return result
