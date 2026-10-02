"""Two-turn bounded loop acceptance on pinned Langflow, with private evidence."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

from lfx.graph.graph.base import Graph

sys.path.insert(0, str(Path(__file__).parent))
from build_flow import build_controller


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--approved-two-turns", action="store_true")
    parser.add_argument("--runner-url", required=True)
    parser.add_argument("--state-directory", type=Path, required=True)
    args = parser.parse_args()
    if not args.approved_two_turns:
        parser.error("explicit additional two-turn approval required")
    state = args.state_directory.resolve()
    if any((parent / ".git").exists() for parent in (state, *state.parents)):
        parser.error("execution state must remain outside Git")
    state.mkdir(parents=True, exist_ok=True)
    before = set(state.glob("*.json"))
    flow = build_controller(state_directory=str(state),
        endpoints_json=json.dumps({"codex": args.runner_url}),
        max_iterations=2, turn_budget=2, deadline_seconds=480,
        stop_answer="LAOMEDO_LOOP_28_COMPLETE")
    await Graph.from_payload(flow).arun(inputs=[{"input_value":
        "Return exactly this instruction for the next iteration, and nothing else: "
        "Reply with exactly LAOMEDO_LOOP_28_COMPLETE."}], types=["chat"])
    created = set(state.glob("*.json")) - before
    if len(created) != 1:
        raise RuntimeError("one_execution_record_required")
    result = json.loads(created.pop().read_text())
    runs = [item.get("run") or {} for item in result["transitions"]]
    if (result["stop_reason"] != "success" or result["submitted_turns"] != 2 or
            len(runs) != 2 or any(run.get("status") != "completed" for run in runs) or
            runs[-1].get("answer") != "LAOMEDO_LOOP_28_COMPLETE" or
            runs[0].get("thread_id") == runs[1].get("thread_id")):
        raise RuntimeError("bounded_loop_acceptance_failed")
    print(json.dumps({"execution_id": result["execution_id"],
        "stop_reason": result["stop_reason"], "submitted_turns": result["submitted_turns"],
        "runs": [{key: run.get(key) for key in
                  ("run_id", "thread_id", "status", "post_run_hash")} for run in runs]}))


if __name__ == "__main__":
    asyncio.run(main())
