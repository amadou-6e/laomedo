"""Real older-image capability refusal, without login copying or model prompts."""

import asyncio
import json
from pathlib import Path
import sys
import tempfile
import threading

ROOT = Path("C:/CodeWorkspace/laomedo")
sys.path.insert(0, str(ROOT / ".tools/worktrees/assistant-tools-293/src"))
from laomedo.agents.agents.codex.controller.models import CodexLaunch
from laomedo.agents.agents.codex.runtime import CodexAgentRuntime
from laomedo.agents.agents.base.models import NativeCommandInvocation
from laomedo.agents.errors import RunnerError


async def main():
    with tempfile.TemporaryDirectory(prefix="native293-capability-") as tmp:
        root = Path(tmp)
        for name in ("workspace", "canonical", "store", "evidence"):
            (root / name).mkdir()
        controller = CodexAgentRuntime(
            CodexLaunch(
                workspace=root / "workspace",
                canonical=root / "canonical",
                store_mount=root / "store",
                image="sha256:3fdc5c4fd643d5f9f5c7f08ed3cd9face2ab277d44260668e837b0132aa2112f",
            ),
            root / "evidence",
        )
        try:
            await controller.initialize()
            assert controller.native_commands_supported is False
            assert controller.command_catalog() is None
            try:
                await controller.prompt(
                    "/status",
                    skills=[],
                    cancelled=threading.Event(),
                    seconds=5,
                    command=NativeCommandInvocation(
                        name="status", catalog_revision="0" * 64
                    ),
                )
            except RunnerError as exc:
                assert exc.code == "native_command_not_supported"
            else:
                raise AssertionError("older adapter accepted native command")
            assert not controller.events
        finally:
            await controller.close()
        assert controller.cleanup_confirmed
        print(
            json.dumps(
                {
                    "older_image_admitted_for_ordinary_protocol": True,
                    "native_commands_supported": False,
                    "catalog_available": False,
                    "command_refused_before_prompt": True,
                    "model_turns": 0,
                    "cleanup_confirmed": True,
                }
            )
        )


asyncio.run(main())
