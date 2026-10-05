"""Pinned Langflow stage protocol for a network-disabled Docker worker.

The host reserves and dispatches the run. This process never receives the
grant store, GitHub login, Langflow API token, or provider credentials.
"""

import asyncio
from contextlib import redirect_stdout
from hashlib import sha256
import json
from pathlib import Path
import sys

from laomedo.langflow_stage_adapter import FrozenLangflowStage


PREFIX = "LAOMEDO_STAGE:"


def _emit(payload):
    print(PREFIX + json.dumps(payload, sort_keys=True), flush=True)


def main():
    try:
        exported = json.loads(Path("/flow/flow.json").read_text(encoding="utf-8"))
        with redirect_stdout(sys.stderr):
            stage = FrozenLangflowStage(exported)
        graph_json = json.dumps(stage.graph_data, sort_keys=True,
                                separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        _emit({"type": "ready", "graph_revision": "sha256:" + sha256(graph_json).hexdigest(),
               "component_revisions": stage.component_revisions})
        command = json.loads(sys.stdin.readline())
        if not isinstance(command, dict) or command.get("type") != "execute":
            raise ValueError("invalid_stage_command")
        with redirect_stdout(sys.stderr):
            result = asyncio.run(stage.graph.arun(inputs=command.get("inputs"),
                types=command.get("types"), outputs=command.get("outputs")))
        _emit({"type": "complete", "result": str(result)})
    except Exception as exc:
        _emit({"type": "failed", "category": type(exc).__name__})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
