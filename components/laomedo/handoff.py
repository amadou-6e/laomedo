"""Select task and provenance explicitly between two agent nodes."""
from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema import Data, Message
from uuid import uuid4


class LaomedoHandoff(Component):
    display_name = "Laomedo Agent Handoff"
    description = "Pass a completed answer with selected run provenance to a fresh agent."
    icon = "ArrowRight"
    name = "LaomedoHandoff"
    inputs = [DataInput(name="origin", display_name="Origin Run", required=True),
              MessageTextInput(name="task", display_name="Task Override", advanced=True),
              DataInput(name="artifacts", display_name="Selected Artifacts", is_list=True, advanced=True)]
    outputs = [Output(name="task_message", display_name="Task", method="task_output", group_outputs=True),
               Output(name="provenance", display_name="Provenance", method="provenance_output", group_outputs=True)]

    def _selected(self):
        source = getattr(self.origin, "data", self.origin)
        if not isinstance(source, dict) or source.get("status") != "completed":
            raise ValueError("completed_origin_required")
        task = getattr(self.task, "text", self.task) or source.get("answer")
        if not isinstance(task, str) or not task.strip():
            raise ValueError("handoff_task_required")
        if not getattr(self, "_execution_id", None):
            self._execution_id = str(uuid4())
        selected = getattr(self, "artifacts", None) or []
        if not isinstance(selected, list):
            selected = [selected]
        selected = [getattr(value, "data", value) for value in selected]
        return task, {"execution_id": self._execution_id, "step": 1,
                      "source": {"run_id": source.get("run_id"),
                                 "provider": source.get("provider", "codex")},
                      "workspace_policy": "independent", "artifact_refs": selected}

    def _pre_run_setup(self):
        self._execution_id = str(uuid4())

    def task_output(self) -> Message:
        task, _ = self._selected()
        return Message(text=task)

    def provenance_output(self) -> Data:
        _, provenance = self._selected()
        return Data(data=provenance)
