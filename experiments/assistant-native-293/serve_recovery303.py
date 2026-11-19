"""Owned preview with explicitly authorized process-only session credential."""

import os
from pathlib import Path
import runpy
import sys


root = Path("C:/CodeWorkspace/laomedo")
implementation = root / ".tools/worktrees/assistant-recovery-303"
os.environ["LAOMEDO_ACCEPTANCE_IMPLEMENTATION"] = str(implementation)
sys.path.insert(0, str(implementation / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "docker-boundary-277"))
from acceptance import session_login
from laomedo.agents.registry import AgentProviderRegistry

original = AgentProviderRegistry.create_agent


def create_agent(provider, *args, **kwargs):
    if provider == "codex":
        kwargs.update(session_login())
    return original(provider, *args, **kwargs)


AgentProviderRegistry.create_agent = create_agent
sys.argv = ["serve", "--resume"]
runpy.run_path(str(Path(__file__).resolve().parents[1] / "assistant-291/serve.py"), run_name="__main__")
