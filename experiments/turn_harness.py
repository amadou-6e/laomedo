"""Opt-in bounds for isolated verification; never imported by normal runners/services.

These subclasses preserve legacy experiment controls without installing their
global limits in user-facing runtime defaults or managed startup configuration.
"""
from laomedo.agents.agents.codex.runner import CodexRunner as LocalRunner; from laomedo.agents.errors import RunnerError; from laomedo.agents.agents.base.utils import _json; from laomedo.agents.agents.base.utils import _read
from laomedo.agents.agents.opencode.runner import OpenCodeRunner


class VerificationTurnBounds:
    def __init__(self, *args, max_model_turns=0, **kwargs):
        if type(max_model_turns) is not int or max_model_turns < 0:
            raise RunnerError("invalid_turn_cap")
        self.max_model_turns = max_model_turns
        super().__init__(*args, **kwargs)

    def _turn_available(self):
        ledger = self.state / "turn-ledger.json"
        value = _read(ledger) if ledger.exists() else {"attempted_turns": 0}
        count = value.get("attempted_turns")
        if type(count) is not int or count < 0:
            raise RunnerError("invalid_turn_ledger")
        if count >= self.max_model_turns:
            raise RunnerError("model_turn_cap_reached")

    def _reserve_turn(self):
        self._turn_available()
        ledger = self.state / "turn-ledger.json"
        count = _read(ledger).get("attempted_turns", 0) if ledger.exists() else 0
        _json(ledger, {"attempted_turns": count + 1,
                       "max_authorized_turns": self.max_model_turns})
        return count + 1


class VerificationLocalRunner(VerificationTurnBounds, LocalRunner):
    pass


class VerificationOpenCodeRunner(VerificationTurnBounds, OpenCodeRunner):
    pass
