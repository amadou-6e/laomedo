from lfx.custom.custom_component.component import Component
from lfx.io import DataInput; from lfx.io import Output
from lfx.schema import Data


class PROperationResult(Component):
    display_name = "Inspect PR operation result"
    inputs = [DataInput(name="result", display_name="Operation Result", required=True)]
    outputs = [Output(name="outcome", display_name="Result", method="result_output")]

    def result_output(self) -> Data:
        return self.result
