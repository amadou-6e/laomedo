"""Deterministic two-stage Langflow fixture; no provider or model calls."""

import time
from pathlib import Path

from lfx.custom.custom_component.component import Component
from lfx.io import MessageTextInput, Output, StrInput
from lfx.schema.message import Message


class PauseForEdit(Component):
    display_name = "EXP-03 pause"
    name = "Exp03Pause"
    inputs = [MessageTextInput(name="task", display_name="Task", required=True),
              StrInput(name="gate", display_name="Gate", required=True)]
    outputs = [Output(name="result", display_name="Result", method="invoke")]

    def invoke(self) -> Message:
        gate = Path(str(self.gate))
        gate.with_suffix(".entered").write_text("entered", encoding="utf-8")
        deadline = time.monotonic() + 90
        while not gate.exists():
            if time.monotonic() > deadline:
                raise TimeoutError("EXP-03 gate was not released")
            time.sleep(0.1)
        return Message(text=str(getattr(self.task, "text", self.task)))


class MarkerAfterPause(Component):
    display_name = "EXP-03 marker"
    name = "Exp03Marker"
    inputs = [MessageTextInput(name="value", display_name="Value", required=True),
              StrInput(name="marker", display_name="Marker", required=True)]
    outputs = [Output(name="result", display_name="Result", method="invoke")]

    def invoke(self) -> Message:
        return Message(text=f"{getattr(self.value, 'text', self.value)}|{self.marker}")
