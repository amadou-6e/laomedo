"""Error types for skills / sources."""

from __future__ import annotations


class SourceError(ValueError):
    """Only closed, nonsecret error codes may cross the service boundary."""
