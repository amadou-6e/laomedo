"""Harmless read-only tools with private acceptance counters."""

import argparse
import asyncio
import json
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP

parser = argparse.ArgumentParser()
parser.add_argument("--state", type=Path, required=True)
parser.add_argument("--port", type=int)
args = parser.parse_args()
server = FastMCP("mcp-280-acceptance", host="127.0.0.1", port=args.port or 8000)


@server.tool()
async def read_marker(ctx: Context) -> str:
    """Read the validation marker. Takes no arguments and has no external effects."""
    state = json.loads(args.state.read_text(encoding="utf-8"))
    if state.get("upstream_canary"):
        request = ctx.request_context.request
        state["upstream_auth_observed"] = (
            request.headers.get("X-MCP-Validation-Key") == state["upstream_canary"]
        )
        if not state["upstream_auth_observed"]:
            raise ValueError("validation_upstream_auth_required")
    state["entered"] = state.get("entered", 0) + 1
    args.state.write_text(json.dumps(state), encoding="utf-8")
    if state.get("hold"):
        # Bounded only in this acceptance server, never in the normal runner.
        await asyncio.sleep(120)
    state["calls"] += 1
    args.state.write_text(json.dumps(state), encoding="utf-8")
    return state["marker"]


@server.tool()
def unselected_probe() -> str:
    """An unselected test tool. This tool should never be available to the agent."""
    state = json.loads(args.state.read_text(encoding="utf-8"))
    state["unselected_calls"] += 1
    args.state.write_text(json.dumps(state), encoding="utf-8")
    return "unselected"


if __name__ == "__main__":
    server.run(transport="streamable-http" if args.port else "stdio")
