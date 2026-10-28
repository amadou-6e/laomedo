"""Error types for agents / workflow."""

from __future__ import annotations


class LaunchError(RuntimeError):
    """A workflow launch or durable run transition could not be accepted.

    ``code`` identifies the existing refusal. An existing reservation or
    dispatch must be reconciled before creating another invocation."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ExternalOutcomeUnknown(RuntimeError):
    """A dispatched external call may have run; its outcome is unconfirmed.

    ``code`` retains the supplied category. Reconcile the existing operation
    instead of treating this exception as proof that retry is safe."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
