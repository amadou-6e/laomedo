"""Output Contract node backed by the installed Laomedo shared evaluator."""

import json

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput; from lfx.io import MultilineInput; from lfx.io import Output
from lfx.schema import Data
from laomedo.agents.interface.output.utils import evaluate_envelope; from laomedo.agents.interface.output.utils import requirements


class LaomedoOutputContract(Component):
    display_name = "Laomedo Output Contract"
    description = "Configure an output form, expose its pinned precheck requirements and validate submissions and route success, failure, rejection or recovery."
    icon = "ClipboardCheck"
    name = "LaomedoOutputContract"
    inputs = [MultilineInput(name="requirements_json", display_name="Output Form", value='{"schema_version":1,"fields":[]}'),
              DataInput(name="agent_submission", display_name="Agent Submission")]
    outputs = [Output(name=key, display_name=key.title(), method=key, group_outputs=True)
               for key in ("success", "failure", "rejection", "recovery")]

    def requirements_output(self) -> Data:
        try:
            specification = json.loads(self.requirements_json)
        except (TypeError, ValueError):
            raise ValueError("invalid_output_requirements_json") from None
        return Data(data=requirements(specification))

    def validation_output(self) -> Data:
        reference = self.requirements_output().data
        envelope = getattr(self.agent_submission, "data", self.agent_submission)
        result = evaluate_envelope(reference, envelope)
        self.status = result["contract_status"]
        return Data(data=result)

    def _pre_run_setup(self):
        self._routing_result = None

    def _route(self, selected):
        from laomedo.integrations.langflow.output.utils import verified_route_submission; from laomedo.integrations.langflow.output.utils import route_destination
        from copy import deepcopy
        cached = getattr(self, "_routing_result", None)
        if cached is None:
            envelope = getattr(self.agent_submission, "data", self.agent_submission)
            verified = verified_route_submission(self, envelope)
            validation = evaluate_envelope(self.requirements_output().data, verified)
            cached = (route_destination(validation), validation)
            self._routing_result = deepcopy(cached)
        destination, validation = deepcopy(cached)
        if selected != destination:
            self.stop(selected)
            return Data(data={})
        self.status = destination
        return Data(data={"route": destination, "validation": validation})

    def success(self) -> Data:
        return self._route("success")

    def failure(self) -> Data:
        return self._route("failure")

    def rejection(self) -> Data:
        return self._route("rejection")

    def recovery(self) -> Data:
        return self._route("recovery")
