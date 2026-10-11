"""Demo destinations. Publication is simulated and never calls GitHub."""
from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output, StrInput
from lfx.schema import Data


class DemoDestination(Component):
    display_name = "Demo destination (simulated)"
    name = "DemoDestination"
    inputs = [DataInput(name="routed", display_name="Routed outcome", required=True),
              DataInput(name="snapshot", display_name="Frozen issue", required=True),
              StrInput(name="destination", display_name="Destination", required=True)]
    outputs = [Output(name="record", display_name="Evidence", method="record_output")]

    def record_output(self) -> Data:
        routed = self.routed.data
        destination = str(self.destination)
        if not routed or routed.get("route") != destination:
            raise ValueError("inactive_destination_must_not_execute")
        return Data(data={"destination": destination, "routed": routed,
                          "issue_snapshot": self.snapshot.data,
                          "publication": {"mode": "simulated", "draft": True,
                                          "reference": "simulation:fixture-draft-pr"}
                                         if destination == "success" else None})
