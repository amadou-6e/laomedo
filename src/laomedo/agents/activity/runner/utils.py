"""Allowlist native telemetry attributes before retention."""

from __future__ import annotations

from laomedo.agents.activity.runner.settings import ALLOWED


def attributes(values):
    result = {}
    for pair in values:
        if pair.key not in ALLOWED:
            continue
        kind = pair.value.WhichOneof("value")
        if kind in {"string_value", "int_value", "double_value", "bool_value"}:
            result[pair.key] = getattr(pair.value, kind)
    return result
