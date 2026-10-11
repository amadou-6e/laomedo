"""Conditional graph routing. Inactive branches are stopped by Langflow."""
from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema import Data


class ContractRoute(Component):
    display_name = "Contract outcome routing"
    name = "ContractRoute"
    inputs = [DataInput(name="validation", display_name="Validation", required=True)]
    outputs = [Output(name=key, display_name=key.title(), method=key, group_outputs=True)
               for key in ("success", "failure", "rejection", "recovery")]

    def _route(self, selected):
        record = self.validation.data
        submission = record.get("agent_submission", {})
        if record.get("contract_status") != "accepted":
            destination = "rejection"
        elif (submission.get("executor_status") != "completed" or
              submission.get("evidence_complete") is not True or
              submission.get("task_outcome") not in {"success", "failure"}):
            destination = "recovery"
        else:
            destination = "success" if submission["task_outcome"] == "success" else "failure"
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

    def recovery(self) -> Data:
        return self._route("recovery")
