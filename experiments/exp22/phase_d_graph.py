"""Pinned Langflow graph child for the bounded Phase D Stop probe.

This file runs inside the pinned Langflow image. It never reads the runner token
itself; the saved component reads its read-only token mount.
"""

import argparse
import asyncio
import json
from pathlib import Path
import time

from lfx.graph.graph.base import Graph


FLOW = Path("/workspace/examples/native-codex-node/flow.json")


async def run(args):
    state = args.state
    flow = json.loads(FLOW.read_text(encoding="utf-8"))
    nodes = {item["data"]["type"]: item for item in flow["data"]["nodes"]}
    skill = nodes["LaomedoSkill"]["data"]["node"]["template"]
    agent = nodes["LaomedoCodexAgent"]["data"]["node"]["template"]
    skill["skill_id"]["value"] = args.skill_id
    skill["revision_id"]["value"] = args.revision_id
    agent["runner_url"]["value"] = f"http://host.docker.internal:{args.runner_port}"
    agent["timeout_seconds"]["value"] = 120
    agent["operation"]["value"] = "fresh"
    graph = Graph.from_payload(flow)
    task_text = (state / "task.txt").read_text(encoding="utf-8")
    graph_task = asyncio.create_task(graph.arun(
        inputs=[{"input_value": task_text}], types=["chat"],
        outputs=["ChatOutput-laomedo", "ChatOutput-run-reference"]))
    (state / "graph-started.json").write_text(json.dumps({
        "started_monotonic": time.monotonic(), "vertices": len(graph.vertices),
        "flow_id": flow["id"]}), encoding="utf-8")
    result = {"stop_signal_seen": False, "graph_outcome": "unknown"}
    try:
        deadline = time.monotonic() + 125
        while time.monotonic() < deadline and not graph_task.done():
            if (state / "stop.signal").exists():
                result["stop_signal_seen"] = True
                result["signal_monotonic"] = time.monotonic()
                graph_task.cancel()
                break
            await asyncio.sleep(.05)
        if not graph_task.done() and not result["stop_signal_seen"]:
            graph_task.cancel()
            result["graph_outcome"] = "deadline_cancelled"
        try:
            await graph_task
        except asyncio.CancelledError:
            result["graph_outcome"] = "cancelled"
        except Exception as exc:
            result["graph_outcome"] = "error"
            result["error_class"] = type(exc).__name__
        else:
            result["graph_outcome"] = "completed"
        # The component keeps its matching remote-cancel task alive after graph
        # cancellation. Give that task time to reach runner terminal evidence.
        if result["stop_signal_seen"]:
            await asyncio.sleep(8)
    finally:
        result["finished_monotonic"] = time.monotonic()
        (state / "graph-result.json").write_text(json.dumps(result, indent=2),
                                                   encoding="utf-8")
    print(json.dumps(result))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--runner-port", type=int, required=True)
    parser.add_argument("--skill-id", required=True)
    parser.add_argument("--revision-id", required=True)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
