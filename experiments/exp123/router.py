"""Use Langflow branch exclusion to route failure to a distinct agent vertex."""
import json
from lfx.custom.custom_component.component import Component
from lfx.io import MessageTextInput, Output
from lfx.schema import Message
from experiments.exp123.runtime import node_event


class Exp123Router(Component):
    display_name = "EXP-123 check branch"
    name = "Exp123Router"
    inputs = [MessageTextInput(name="check", display_name="Check result", required=True)]
    outputs = [Output(name="success", display_name="Passed", method="on_success", group_outputs=True),
               Output(name="failure", display_name="Failed", method="on_failure", group_outputs=True)]

    def route(self, requested: str) -> Message:
        payload = json.loads(self.check)
        chosen = "failure" if payload["status"] == "failed" else "success"
        blocked = "success" if chosen == "failure" else "failure"
        self.stop(blocked)
        self.graph.exclude_branch_conditionally(self._id, output_name=blocked)
        if requested == chosen:
            node_event(payload["run_id"], "branch_selected", self._id,
                       str(self.graph.run_id), chosen=chosen)
            return Message(text=json.dumps(payload, sort_keys=True))
        return Message(text="")

    def on_success(self) -> Message:
        return self.route("success")

    def on_failure(self) -> Message:
        return self.route("failure")
