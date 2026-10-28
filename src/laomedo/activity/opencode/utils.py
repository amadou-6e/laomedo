"""Bound and sanitize native OpenCode event frames."""

from __future__ import annotations

import json
import laomedo.activity.opencode.settings as _opencode_settings
import re


def sanitized(value):
    if isinstance(value, dict):
        return {
            key: (
                "[redacted]"
                if key.lower() in _opencode_settings.SECRET_KEYS
                else sanitized(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitized(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/-]+", "Bearer [redacted]", value)
    return value


def frames(response):
    """SSE data can span multiple lines; comments and heartbeats aren't actions."""
    data, size = [], 0
    while True:
        line = response.readline(1024 * 1024 + 1)
        if not line:
            return
        size += len(line)
        if size > 1024 * 1024:
            raise ValueError("opencode_sse_frame_size_limit")
        line = line.decode("utf-8").rstrip("\r\n")
        if not line:
            if data:
                yield json.loads("\n".join(data))
            data, size = [], 0
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
