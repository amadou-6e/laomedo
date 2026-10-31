"""Run-local MCP transport. The host executes tools in a credential-free worker."""

import json
import os
import sys
from urllib.request import Request
from urllib.request import urlopen

for line in sys.stdin:
    try:
        request = json.loads(line)
        identity = request.get("id")
        method = request.get("method")
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "laomedo-workspace", "version": "1"},
            }
        elif method == "tools/list":
            tools = [
                {
                    "name": "exec_command",
                    "description": "Run a shell command in the draft workspace. No credentials or network are available.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                        "additionalProperties": False,
                    },
                }
            ]
            if os.environ.get("LAOMEDO_GITHUB_GRANTED") == "1":
                tools.append(
                    {
                        "name": "github_operation",
                        "description": "Request a host-authorized GitHub operation. Never retry an uncertain write.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "operation": {"type": "string"},
                                "payload": {"type": "object"},
                                "effect_id": {"type": "string"},
                            },
                            "required": ["operation", "payload"],
                            "additionalProperties": False,
                        },
                    }
                )
            result = {"tools": tools}
        elif method == "tools/call":
            params = request.get("params", {})
            if params.get("name") not in {"exec_command", "github_operation"}:
                raise ValueError("unknown_workspace_tool")
            arguments = params.get("arguments", {})
            payload = json.dumps(
                {"github": arguments}
                if params["name"] == "github_operation"
                else arguments
            ).encode()
            token = open("/run/laomedo/command-token", encoding="ascii").read().strip()
            call = Request(
                os.environ["LAOMEDO_COMMAND_URL"],
                data=payload,
                headers={
                    "Authorization": "Bearer " + token,
                    "Content-Type": "application/json",
                },
            )
            with urlopen(call, timeout=125) as response:
                value = json.load(response)
            result = {
                "content": [{"type": "text", "text": json.dumps(value)}],
                "isError": bool(value.get("error")) or value.get("exit_code", 0) != 0,
            }
        elif identity is None:
            continue
        else:
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": identity,
                        "error": {"code": -32601, "message": "Unknown method"},
                    }
                ),
                flush=True,
            )
            continue
        print(
            json.dumps({"jsonrpc": "2.0", "id": identity, "result": result}), flush=True
        )
    except Exception:
        # Never send transport errors, tokens, or host paths back to the model.
        print(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": locals().get("identity"),
                    "error": {
                        "code": -32000,
                        "message": "Workspace command unavailable",
                    },
                }
            ),
            flush=True,
        )
