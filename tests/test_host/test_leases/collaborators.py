"""Internal observations for lease HTTP controls; no external authority."""


class RecordingGrantBook:
    """Observe handler forwarding without real credentials or external effects."""

    def __init__(self):
        """Keep only disposable internal authorization observations."""
        self.calls = []

    def check(self, token):
        """Return the existing two-value book interface for an internal token."""
        self.calls.append(token)
        return token == "approved", None


class RecordingMediator:
    """Observe HTTP forwarding and existing exception-to-wire categories."""

    def __init__(self):
        """Initialize task-local observations without services or credentials."""
        self.calls = []
        self.error = None

    def invoke(self, **arguments):
        """Return a small ordered Unicode value or the selected internal failure."""
        self.calls.append(arguments)
        if self.error is not None:
            raise self.error
        return {"nested": {"unicode": "\u00e9"}, "accepted": True}
