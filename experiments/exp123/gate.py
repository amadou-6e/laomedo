"""A waiting vertex inside the existing Langflow graph; no agent dispatch."""
import asyncio
import json
import time
from lfx.custom.custom_component.component import Component
from lfx.io import MessageTextInput, Output
from lfx.schema import Message
from experiments.exp123.runtime import fetch_observation, node_event


class Exp123Gate(Component):
    display_name = "EXP-123 wait for check"
    name = "Exp123Gate"
    inputs = [MessageTextInput(name="delivery", display_name="PR delivery", required=True)]
    outputs = [Output(name="result", display_name="Check result", method="wait_for_check")]

    async def wait_for_check(self) -> Message:
        payload = json.loads(self.delivery)
        run = payload["run_id"]
        gate = run + ":gate-" + str(payload["iteration"])
        graph = str(self.graph.run_id)
        node_event(run, "gate_waiting", self._id, graph, gate_id=gate,
                   head_sha=payload["head_sha"])
        deadline = time.monotonic() + 12
        try:
            while time.monotonic() < deadline:
                observation = await asyncio.to_thread(fetch_observation, run, gate,
                                                     payload["head_sha"])
                if observation["status"] in ("passed", "failed"):
                    result = {**payload, **observation, "gate_id": gate}
                    node_event(run, "gate_decided", self._id, graph, gate_id=gate,
                               head_sha=payload["head_sha"], status=result["status"],
                               source_check_id=result["source_check_id"])
                    return Message(text=json.dumps(result, sort_keys=True))
                await asyncio.sleep(.1)
            node_event(run, "gate_deadline", self._id, graph, gate_id=gate)
            raise TimeoutError("check_result_pending")
        except asyncio.CancelledError:
            node_event(run, "gate_cancelled", self._id, graph, gate_id=gate)
            raise
