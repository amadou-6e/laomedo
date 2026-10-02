"""Synthetic Langflow stage for UI-disconnect and backend-kill testing."""

from pathlib import Path
import sys
import time

from lfx.custom.custom_component.component import Component
from lfx.io import MessageTextInput, Output, StrInput
from lfx.schema.message import Message

sys.path.insert(0, "/laomedo-src")
from laomedo.workflow_run_store import WorkflowRunStore


class Exp06Stage(Component):
    display_name = "EXP-06 synthetic stage"
    name = "Exp06Stage"
    inputs = [MessageTextInput(name="task", display_name="Task", required=True),
              StrInput(name="mode", display_name="Mode", required=True)]
    outputs = [Output(name="result", display_name="Result", method="invoke")]

    def invoke(self) -> Message:
        mode = str(self.mode)
        if mode not in {"ui", "crash"}:
            raise ValueError("invalid_exp06_mode")
        state = Path("/state")
        store = WorkflowRunStore(state / "runs.sqlite3")
        record = store.reserve(
            graph={"nodes": [{"id": "Exp06Stage-exp06"}]},
            component_code={"Exp06Stage-exp06": "EXP06_SYNTHETIC_STAGE_V1"},
            resolved_config={"mode": mode},
            trigger={"type": "direct", "task": str(getattr(self.task, "text", self.task))},
        )

        def wait_for_release(run_id):
            (state / f"entered-{mode}").write_text(run_id, encoding="utf-8")
            deadline = time.monotonic() + 120
            while not (state / f"release-{mode}").exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError("EXP-06 gate not released")
                time.sleep(0.1)
            (state / f"callback-{mode}").write_text(run_id, encoding="utf-8")
            return run_id

        run_id = store.dispatch(record["run_id"], wait_for_release)
        return Message(text=f"{mode}:{run_id}")
