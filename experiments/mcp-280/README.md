# Real graph MCP acceptance

`server.py` exposes a harmless marker reader and an unselected probe tool over
STDIO or HTTP. A private marker/counter file proves an actual upstream call;
model text alone is not acceptance.

`graph_case.py` registers that server through the isolated Langflow app, builds a
native MCP Toolset-to-Agent graph, submits it through the session API and polls
the real runner. It prints only sanitized outcomes. Credentials and API responses
remain in memory; private runtime files remain outside Git.

Use only explicitly authorized provider profiles. A successful local transport
test does not establish real provider acceptance or actual editor rendering.
