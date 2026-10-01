"""Select task and provenance explicitly between two agent nodes."""
from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema import Data, Message


class LaomedoHandoff(Component):
    display_name = "Laomedo Agent Handoff"
    description = "Pass a completed answer with selected run provenance to a fresh agent."
    icon = "ArrowRight"
    name = "LaomedoHandoff"
    inputs = [DataInput(name="origin", display_name="Origin Run", required=True),
              MessageTextInput(name="task", display_name="Task Override", advanced=True)]
    outputs = [Output(name="task_message", display_name="Task", method="task_output", group_outputs=True),
               Output(name="provenance", display_name="Provenance", method="provenance_output", group_outputs=True)]

    def _selected(self):
        source = getattr(self.origin, "data", self.origin)
        if not isinstance(source, dict) or source.get("status") != "completed":
            raise ValueError("completed_origin_required")
        task = getattr(self.task, "text", self.task) or source.get("answer")
        if not isinstance(task, str) or not task.strip():
            raise ValueError("handoff_task_required")
        return task, {"source_run_id": source.get("run_id"),
                      "source_provider": source.get("provider", "codex"),
                      "workspace_policy": "independent", "operation": "fresh"}

    def task_output(self) -> Message:
        task, _ = self._selected()
        return Message(text=task)

    def provenance_output(self) -> Data:
        _, provenance = self._selected()
        return Data(data=provenance)
