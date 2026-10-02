"""Two-turn live graph acceptance. Explicit approval flag, no retries or auth copy."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

from lfx.graph.graph.base import Graph

sys.path.insert(0, str(Path(__file__).parent))
from build_flow import build


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--approved-two-turns", action="store_true")
    parser.add_argument("--runner-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.approved_two_turns:
        parser.error("explicit two-turn approval required")
    output = args.output.resolve()
    if any((parent / ".git").exists() for parent in (output.parent, *output.parents)):
        parser.error("live output must remain outside Git")
    flow = build()
    nodes = flow["data"]["nodes"]
    for node in nodes:
        if node["data"]["type"] == "LaomedoCodexAgent":
            fields = node["data"]["node"]["template"]
            fields["runner_url"]["value"] = args.runner_url
            fields["timeout_seconds"]["value"] = 240
    # Private full graph results stay in the caller-selected private scratch path.
    result = await Graph.from_payload(flow).arun(inputs=[{"input_value":
        "Your only task is to provide instructions for another agent. Return exactly this sentence "
        "and nothing else: Reply with exactly LAOMEDO_CHAIN_28_COMPLETE."}], types=["chat"])
    output.write_text(str(result), encoding="utf-8")
    if "LAOMEDO_CHAIN_28_COMPLETE" not in str(result):
        raise RuntimeError("chain_marker_missing")
    print("two_agent_chain_marker_observed")


if __name__ == "__main__":
    asyncio.run(main())
