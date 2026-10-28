"""Error types for agents / workflow."""

from __future__ import annotations


class LaunchError(RuntimeError):
    pass


class ExternalOutcomeUnknown(RuntimeError):
    """A dispatched external call may have run, but its result is unconfirmed."""
