"""Deterministic Agent fixture: no model, credentials or provider calls."""

from lfx.custom.custom_component.component import Component
from lfx.io import StrInput
from lfx.io import DropdownInput
from lfx.io import Output
from lfx.schema import Data


class PRFixtureAgent(Component):
    display_name = "Agent (fixture)"
    description = "Read the PR task and return one operation. This is a deterministic fixture, not a model."
    name = "PRFixtureAgent"
    inputs = [
        StrInput(
            name="task",
            display_name="PR Task",
            input_types=["Data", "Message"],
            required=True,
        ),
        DropdownInput(
            name="action",
            display_name="Operation",
            value="modify",
            options=["modify", "close", "invalid", "fail"],
        ),
    ]
    outputs = [
        Output(
            name="preview",
            display_name="Received PR",
            method="preview_output",
            group_outputs=True,
        ),
        Output(
            name="operation",
            display_name="Operation",
            method="operation_output",
            group_outputs=True,
        ),
    ]

    def preview_output(self) -> Data:
        return Data(data={"text": self._task_text()})

    def operation_output(self) -> Data:
        self.update_ctx(
            {
                "pr_fixture_agent_calls": self.ctx.get("pr_fixture_agent_calls", 0) + 1,
                "pr_fixture_agent_task": self._task_text(),
            }
        )
        if self.action == "fail":
            raise ValueError("fixture_agent_failure")
        if self.action == "invalid":
            return Data(data={"unexpected": "not an operation"})
        operation = {"action": self.action}
        if self.action == "modify":
            operation["changes"] = {
                "title": "PR operation verified",
                "body": "Updated through the two-node PR/Agent loop.",
            }
        return Data(data=operation)

    def _task_text(self):
        """Use the production PR adapter for structured reads and native loop text."""
        from lfx.schema import Message
        from laomedo.github.pull_requests.context import task_text

        return (
            self.task.text if isinstance(self.task, Message) else task_text(self.task)
        )
