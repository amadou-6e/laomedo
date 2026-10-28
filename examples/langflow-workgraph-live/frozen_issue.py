"""A host-frozen real issue enters the graph without GitHub credentials."""
import base64
import hashlib
import json
from lfx.custom.custom_component.component import Component
from lfx.io import Output; from lfx.io import StrInput; from lfx.io import MultilineInput; from lfx.io import NestedDictInput
from lfx.schema import Data; from lfx.schema import Message


class FrozenIssue(Component):
    display_name = "Frozen GitHub issue"
    name = "FrozenIssue"
    description = "Read a host-frozen issue snapshot and pass readable task instructions to the agent. This node does not fetch GitHub."
    inputs = [
        StrInput(name="issue_url", display_name="Selected issue URL",
                 info="This demo uses a host-frozen issue. Changing this URL alone does not fetch another issue."),
        NestedDictInput(name="task_data", display_name="Task", info="Edit the instructions entry. Structured text preserves literal backslashes."),
        MultilineInput(name="task_text", display_name="Legacy text task", advanced=True),
        NestedDictInput(name="snapshot_data", display_name="Frozen issue context", advanced=True),
        StrInput(name="snapshot_base64", display_name="Legacy encoded context", advanced=True),
        StrInput(name="task_base64", display_name="Legacy encoded task", advanced=True),
    ]
    outputs = [Output(name="task", display_name="Task", method="task_output", group_outputs=True),
               Output(name="snapshot", display_name="Issue context", method="snapshot_output", group_outputs=True)]

    def _snapshot(self):
        data = getattr(self, "snapshot_data", None)
        value = data if data else json.loads(base64.b64decode(self.snapshot_base64, validate=True).decode("utf-8"))
        context = value["context"]
        canonical = json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        if (value.get("source") != "host_frozen_github" or
                value.get("snapshot_id") != "sha256:" + hashlib.sha256(canonical).hexdigest() or
                not context.get("related_prs_complete") or
                not isinstance(context.get("issue", {}).get("body"), str)):
            raise ValueError("frozen_issue_context_invalid")
        selected = getattr(self, "issue_url", None)
        if selected and selected != context["issue"].get("url"):
            raise ValueError("frozen_issue_selection_mismatch")
        return value

    def task_output(self) -> Message:
        legacy = getattr(self, "task_base64", None)
        fields = getattr(self, "task_data", None) or {}
        plain = fields.get("instructions", getattr(self, "task_text", None) or "")
        if not isinstance(plain, str):
            raise ValueError("issue_task_required")
        task = (plain if plain.strip() else
                base64.b64decode(legacy, validate=True).decode("utf-8") if legacy else "")
        if not task.strip():
            raise ValueError("issue_task_required")
        return Message(text=json.dumps({"task": task, "frozen_issue": self._snapshot()},
                                       sort_keys=True, ensure_ascii=False))

    def snapshot_output(self) -> Data:
        return Data(data=self._snapshot())
