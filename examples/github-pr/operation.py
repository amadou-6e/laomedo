"""Credential-free graph input; its grant resolves only in the fixture host."""
from lfx.custom.custom_component.component import Component
from lfx.io import Output
from lfx.schema import Data


class FixturePROperation(Component):
    display_name = "Fixture PR modify operation"
    description = "Fixture host reference only; no provider credential or model call."
    inputs = []
    outputs = [Output(name="operation", display_name="Operation", method="operation_output")]

    def operation_output(self) -> Data:
        return Data(data={"action": "modify", "request_id": "pr-demo-modify-1", "grant_ref": "fixture-grant",
                          "changes": {"title": "PR operation verified", "body": "Updated through the PR node."}})
