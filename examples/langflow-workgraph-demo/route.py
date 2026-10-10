"""Conditional graph routing. Inactive branches are stopped by Langflow."""
from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema import Data


class ContractRoute(Component):
    display_name = "Contract outcome routing"
    name = "ContractRoute"
    inputs = [DataInput(name="validation", display_name="Validation", required=True)]
    outputs = [Output(name=key, display_name=key.title(), method=key, group_outputs=True)
               for key in ("success", "failure", "rejection")]

    def _route(self, selected):
        record = self.validation.data
        submission = record.get("agent_submission", {})
        destination = ("rejection" if record.get("contract_status") != "accepted" else
                       "success" if (submission.get("task_outcome") == "success" and
                                     submission.get("executor_status") == "completed" and
                                     submission.get("evidence_complete") is True) else "failure")
        if selected != destination:
            self.stop(selected)
            return Data(data={})
        return Data(data={"route": destination, "validation": record})

    def success(self) -> Data:
        return self._route("success")

    def failure(self) -> Data:
        return self._route("failure")

    def rejection(self) -> Data:
        return self._route("rejection")
