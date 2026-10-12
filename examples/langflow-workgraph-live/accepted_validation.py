"""Unwrap the success route for the publisher; this supplies no authority."""
from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema import Data


class AcceptedValidation(Component):
    display_name = "Accepted success validation"
    name = "AcceptedValidation"
    inputs = [DataInput(name="routed", display_name="Success route", required=True)]
    outputs = [Output(name="validation", display_name="Validation", method="validation_output")]

    def validation_output(self) -> Data:
        value = self.routed.data
        if value.get("route") != "success" or not isinstance(value.get("validation"), dict):
            raise ValueError("success_route_required")
        return Data(data=value["validation"])
