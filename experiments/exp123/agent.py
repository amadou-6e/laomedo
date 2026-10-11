"""Synthetic agent vertex: record one invocation and return a fixed PR head."""
import json
from lfx.custom.custom_component.component import Component
from lfx.io import IntInput, MessageTextInput, Output
from lfx.schema import Message
from experiments.exp123.runtime import node_event


class Exp123Agent(Component):
    display_name = "EXP-123 synthetic agent"
    name = "Exp123Agent"
    inputs = [MessageTextInput(name="context", display_name="Context", required=True),
              IntInput(name="iteration", display_name="Iteration", value=1)]
    outputs = [Output(name="delivery", display_name="PR delivery", method="deliver")]

    def deliver(self) -> Message:
        prior = json.loads(self.context)
        index = int(self.iteration)
        if index not in (1, 2):
            raise ValueError("invocation_cap")
        if index == 2 and prior.get("status") != "failed":
            raise ValueError("repair_requires_failed_check")
        payload = {"run_id": prior["run_id"], "repository": "fixture/repo",
                   "pr_number": 1, "head_sha": str(index) * 40,
                   "iteration": index, "invocation_id": prior["run_id"] + ":" + self._id}
        node_event(payload["run_id"], "agent_invoked", self._id,
                   str(self.graph.run_id), **payload)
        return Message(text=json.dumps(payload, sort_keys=True))
