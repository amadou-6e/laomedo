"""Native bounded chain/loop node; requires the Laomedo Python runtime package."""
import asyncio
import json

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, DropdownInput, IntInput, MessageTextInput, Output, StrInput
from lfx.schema import Data, Message


class LaomedoBoundedController(Component):
    display_name = "Laomedo Bounded Agent Controller"
    description = "Explicit finite chains or bounded loops with durable execution records."
    icon = "Repeat"
    name = "LaomedoBoundedController"
    inputs = [
        MessageTextInput(name="task", display_name="Initial Task", required=True),
        DataInput(name="skills", display_name="Skill References", is_list=True, required=True),
        StrInput(name="targets_json", display_name="Targets JSON", required=True,
                 value='[{"provider":"codex","model":"gpt-6-luna","effort":"low"}]'),
        StrInput(name="endpoints_json", display_name="Runner Endpoints JSON", advanced=True,
                 value='{"codex":"http://host.docker.internal:8765"}'),
        DropdownInput(name="mode", display_name="Mode", options=["chain", "loop"], value="chain"),
        StrInput(name="stop_answer", display_name="Exact Success Answer", required=True),
        StrInput(name="artifact_paths_json", display_name="Selected Artifact Paths JSON", value="[]", advanced=True),
        IntInput(name="max_iterations", display_name="Maximum Iterations", value=2),
        IntInput(name="turn_budget", display_name="Aggregate Turn Budget", value=2),
        IntInput(name="deadline_seconds", display_name="Deadline Seconds", value=240),
        StrInput(name="state_directory", display_name="Private Execution State", advanced=True,
                 value="/app/laomedo-state"),
    ]
    outputs = [Output(name="answer", display_name="Last Answer", method="answer_output", group_outputs=True),
               Output(name="execution", display_name="Execution Evidence", method="execution_output", group_outputs=True)]

    def _pre_run_setup(self):
        self._dispatch_task = None
        self._controller = None

    async def _result(self):
        if getattr(self, "_dispatch_task", None) is None:
            from laomedo.handoffs import BoundedController
            from laomedo.handoff_http import RunnerAdapter
            targets = json.loads(self.targets_json)
            if not isinstance(targets, list) or not 1 <= len(targets) <= 16:
                raise ValueError("one_to_sixteen_targets_required")
            for target in targets:
                if (not isinstance(target, dict) or target.get("provider") not in {"codex", "opencode"} or
                        set(target) - {"provider", "agent", "model", "effort"} or
                        not all(isinstance(target.get(key), str) and target[key].strip()
                                for key in ("model", "effort"))):
                    raise ValueError("provider_model_effort_required")
            if not self.stop_answer or self.mode not in {"chain", "loop"}:
                raise ValueError("explicit_stop_and_mode_required")
            skills = self.skills if isinstance(self.skills, list) else [self.skills]
            skills = [getattr(skill, "data", skill) for skill in skills]
            adapter = RunnerAdapter(json.loads(self.endpoints_json))
            artifact_paths = json.loads(getattr(self, "artifact_paths_json", "[]"))
            if not isinstance(artifact_paths, list) or not all(isinstance(path, str) for path in artifact_paths):
                raise ValueError("artifact_path_list_required")
            self._controller = BoundedController(adapter,
                max_iterations=int(self.max_iterations), turn_budget=int(self.turn_budget),
                timeout_seconds=int(self.deadline_seconds), state_dir=self.state_directory)
            task = str(getattr(self.task, "text", self.task) or "")
            self._dispatch_task = asyncio.create_task(asyncio.to_thread(self._controller.run,
                targets, task, skills, success=lambda run: run.get("answer") == self.stop_answer,
                loop=self.mode == "loop", artifacts=lambda source: adapter.select_artifacts(source, artifact_paths)))
        try:
            return await asyncio.shield(self._dispatch_task)
        except asyncio.CancelledError:
            if self._controller is not None:
                await asyncio.to_thread(self._controller.cancel)
            raise

    async def execution_output(self) -> Data:
        result = await self._result()
        self.status = result["stop_reason"]
        return Data(data=result)

    async def answer_output(self) -> Message:
        result = await self._result()
        transitions = result["transitions"]
        run = transitions[-1].get("run") if transitions else None
        return Message(text=(run or {}).get("answer") or "")
