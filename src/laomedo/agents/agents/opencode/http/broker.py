"""Authenticated MCP adaptation for the provider's typed command executor."""

import json
import secrets
import threading
from laomedo.agents.agents.opencode.http.server import BrokerHttpServer
from laomedo.agents.agents.base.models import CommandRequest
from laomedo.agents.errors import RunnerError


class OpenCodeCommandBroker:
    """Own MCP capability/listener state without implementing command execution."""

    def __init__(self, executor):
        """Start one capability-protected listener for its exact command executor."""
        self.executor = executor
        self.token = secrets.token_hex(32)
        self.server = BrokerHttpServer(self, ("0.0.0.0", 0))
        self.server.daemon_threads = True
        try:
            self.thread = threading.Thread(
                target=self.server.serve_forever, daemon=True
            )
            self.thread.start()
        except Exception:
            self.server.server_close()
            raise

    def rpc(self, method, params):
        """Adapt the authenticated MCP methods to typed command execution while preserving native wire result/error shapes."""
        if method == "initialize":
            return {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "laomedo-command-worker", "version": "1"},
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {
                "tools": [
                    {
                        "name": "exec",
                        "description": "Run a shell command in the isolated /draft workspace Docker worker. Credentials are not mounted.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"command": {"type": "string"}},
                            "required": ["command"],
                            "additionalProperties": False,
                        },
                    }
                ]
            }
        if method != "tools/call" or params.get("name") != "exec":
            raise RunnerError("unknown_worker_tool")
        command = params.get("arguments", {}).get("command")
        if not isinstance(command, str) or not command.strip() or len(command) > 16000:
            raise RunnerError("invalid_worker_command")
        result = self.executor.execute(CommandRequest(command=command)).model_dump(
            exclude={"cleanup"}
        )
        return {
            "content": [{"type": "text", "text": json.dumps(result)}],
            "isError": result["exit_code"] != 0,
        }
