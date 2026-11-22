"""Reclassify an existing native export without replaying its command or changing it."""

import argparse
import json
from pathlib import Path

from laomedo.agents.agents.base.models import NativeCommandInvocation
from laomedo.agents.agents.base.agent import BaseAgent
from laomedo.agents.agents.opencode.commands import OpenCodeCommands
from laomedo.agents.agents.opencode.history.models import NativeHistory
from laomedo.agents.errors import RunnerError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("exports", type=Path)
    parser.add_argument("--command", choices=["init", "review"], required=True)
    args = parser.parse_args()
    value = json.loads(args.exports.read_text(encoding="utf-8"))
    history = NativeHistory.model_validate(value["after"])
    baseline = NativeHistory.model_validate(value["before"])
    record = json.loads(
        (args.exports.parent.parent / "record.json").read_text(encoding="utf-8")
    )
    names = BaseAgent.mcp_names(record)
    try:
        OpenCodeCommands.result(
            NativeCommandInvocation(name=args.command, catalog_revision="a" * 64),
            history,
            baseline,
            external_tools=names,
        )
    except RunnerError as error:
        print(error.code)
        return 0 if error.code == "opencode_native_command_failed" else 1
    raise SystemExit("Expected a retained known failure, not success")


if __name__ == "__main__":
    raise SystemExit(main())
