"""Error types for agents / runtime."""

from __future__ import annotations


class RunnerError(ValueError):
    """Runner validation, isolation, native execution or reconciliation failed.

    ``code`` retains the boundary category. Consult the durable run record
    before deciding whether dispatch occurred or retry is safe."""

    def __init__(self, code: str, *, observation=None):
        """Keep legacy args/string while carrying an optional typed private fact."""
        if observation is not None:
            from laomedo.agents.agents.base.models import FailureObservation

            if type(observation) is not FailureObservation:
                raise TypeError("failure_observation_required")
        self.observation = observation
        self.code = code
        super().__init__(code)
