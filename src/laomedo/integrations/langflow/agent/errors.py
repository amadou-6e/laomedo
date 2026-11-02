"""Agent graph invocation failures retaining their public recovery reference."""


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
