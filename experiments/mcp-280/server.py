"""Harmless read-only tools with private acceptance counters."""

import argparse
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

parser = argparse.ArgumentParser()
parser.add_argument("--state", type=Path, required=True)
parser.add_argument("--port", type=int)
args = parser.parse_args()
server = FastMCP("mcp-280-acceptance", host="127.0.0.1", port=args.port or 8000)


@server.tool()
def read_marker() -> str:
    """Read the validation marker. Takes no arguments and has no external effects."""
    state = json.loads(args.state.read_text(encoding="utf-8"))
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
