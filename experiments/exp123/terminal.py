"""Record the observed terminal branch and bounded repair result."""
import json
from lfx.custom.custom_component.component import Component
from lfx.io import MessageTextInput, Output
from lfx.schema import Message
from experiments.exp123.runtime import node_event


class Exp123Terminal(Component):
    display_name = "EXP-123 result"
    name = "Exp123Terminal"
    inputs = [MessageTextInput(name="check", display_name="Check result", required=True)]
    outputs = [Output(name="result", display_name="Result", method="report")]

    def report(self) -> Message:
        payload = json.loads(self.check)
        reason = "checks_passed" if payload["status"] == "passed" else "iteration_cap_exhausted"
        node_event(payload["run_id"], "terminal_result", self._id,
                   str(self.graph.run_id), status=payload["status"], reason=reason)
        return Message(text=json.dumps({**payload, "reason": reason}, sort_keys=True))
