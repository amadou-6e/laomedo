"""Output Contract node backed by the installed Laomedo shared evaluator."""

import json

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MultilineInput, Output
from lfx.schema import Data
from laomedo.output_contract import evaluate_envelope, requirements


class LaomedoOutputContract(Component):
    display_name = "Laomedo Output Contract"
    description = "Configure an output form, expose its pinned precheck requirements and validate agent submissions for graph routing."
    icon = "ClipboardCheck"
    name = "LaomedoOutputContract"
    inputs = [MultilineInput(name="requirements_json", display_name="Output Form", value='{"schema_version":1,"fields":[]}'),
              DataInput(name="agent_submission", display_name="Agent Submission")]
    outputs = [Output(name="requirements", display_name="Precheck Requirements", method="requirements_output", group_outputs=True),
               Output(name="validation", display_name="Validation Outcome", method="validation_output", group_outputs=True)]

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
