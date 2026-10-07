"""Untrusted Langflow validation or execution inside a disposable stage.

The host owns run and status decisions. Anything this process writes to stdout
is untrusted result data, never a control or attestation message.
"""

import asyncio
from contextlib import contextmanager, redirect_stdout
import json
import os
from pathlib import Path
import sys

from laomedo.langflow_stage_adapter import FrozenLangflowStage


@contextmanager
def _component_output():
    """Keep ordinary component chatter out of result data when possible."""
    original = os.dup(1)
    sink = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(sink, 1)
        with redirect_stdout(sys.stderr):
            yield
    finally:
        os.dup2(original, 1)
        os.close(original)
        os.close(sink)


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if arguments not in (["validate"], ["execute"]):
        return 2
    try:
        exported = json.loads(Path("/flow/flow.json").read_text(encoding="utf-8"))
        with _component_output():
            stage = FrozenLangflowStage(exported)
        if arguments == ["validate"]:
            return 0
        command = json.loads(sys.stdin.readline())
        if not isinstance(command, dict) or command.get("type") != "execute":
            return 2
        with _component_output():
            result = asyncio.run(stage.graph.arun(inputs=command.get("inputs"),
                types=command.get("types"), outputs=command.get("outputs")))
        print(str(result), flush=True)
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
