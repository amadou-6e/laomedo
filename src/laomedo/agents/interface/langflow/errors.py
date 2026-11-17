"""Agent graph invocation failures retaining their public recovery reference."""

import json

from laomedo.agents.interface.models import RunnerDiagnostics


class RunnerRequestError(RuntimeError):
    """HTTP failure without a new run; preserves only safe diagnostic observations.

    The stable code remains first in the message. A bounded diagnostic envelope
    supports legacy exception-rendering outputs without exposing HTTP bodies.
    Neither the exception nor its diagnostics confirms whether dispatch occurred.
    """

    def __init__(self, code, diagnostics):
        self.code = code
        self.diagnostics = RunnerDiagnostics.from_payload(diagnostics).to_payload()
        super().__init__(code + "; runner_diagnostics=" + json.dumps(self.diagnostics))


class RunnerResultError(RuntimeError):
    """Failed invocation with the public run reference retained for recovery."""

    def __init__(self, reference, message=None):
        self.run_reference = reference
        self.code = (
            reference.get("error_category") or reference.get("status") or "unknown"
        )
        super().__init__(
            message
            or f"Laomedo run {reference['run_id']} failed: "
            f"{reference.get('error_category') or reference.get('status') or 'unknown'}"
        )
