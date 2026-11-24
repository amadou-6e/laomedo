"""Local read-only MCP integration server; never loads host credentials."""

import sys

from mcp.server.fastmcp import FastMCP

server = FastMCP("local-compatibility", host="127.0.0.1")


@server.tool()
def echo(message: str) -> str:
    """Return the supplied message without external effects or credential access."""
    return message


if __name__ == "__main__":
    if len(sys.argv) == 2:
        server.settings.port = int(sys.argv[1])
        server.run(transport="streamable-http")
    else:
        server.run(transport="stdio")
