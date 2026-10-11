"""A host-frozen real issue enters the graph without GitHub credentials."""
import hashlib
import json
from lfx.custom.custom_component.component import Component
from lfx.io import Output, StrInput
from lfx.schema import Data, Message


class FrozenIssue(Component):
    display_name = "Frozen GitHub issue"
    name = "FrozenIssue"
    inputs = [StrInput(name="snapshot_json", display_name="Frozen context", required=True),
              StrInput(name="task_instruction", display_name="Bounded task", required=True)]
    outputs = [Output(name="task", display_name="Task", method="task_output", group_outputs=True),
               Output(name="snapshot", display_name="Issue context", method="snapshot_output", group_outputs=True)]

    def _snapshot(self):
        value = json.loads(self.snapshot_json)
        context = value["context"]
        canonical = json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        if (value.get("source") != "host_frozen_github" or
                value.get("snapshot_id") != "sha256:" + hashlib.sha256(canonical).hexdigest() or
                not context.get("related_prs_complete") or
                not isinstance(context.get("issue", {}).get("body"), str)):
            raise ValueError("frozen_issue_context_invalid")
        return value

    def task_output(self) -> Message:
        return Message(text=json.dumps({"task": self.task_instruction, "frozen_issue": self._snapshot()},
                                       sort_keys=True, ensure_ascii=False))

    def snapshot_output(self) -> Data:
        return Data(data=self._snapshot())
