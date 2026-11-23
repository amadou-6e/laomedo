"""Run real credential-free Git commands through the OpenCode Docker worker."""

import json
from pathlib import Path
import subprocess
from uuid import uuid4

from laomedo.agents.agents.base.models import CommandRequest
from laomedo.agents.agents.opencode.executor import OpenCodeCommandExecutor
from laomedo.agents.agents.opencode.settings import WORKER_IMAGE

root = Path("C:/CodeWorkspace/laomedo/.tools") / ("assistant-git-trust-" + uuid4().hex)
root.mkdir()
workspace, canonical, store, evidence = [
    root / name for name in ("draft", "canonical", "store", "evidence")
]
for directory in (workspace, canonical, store, evidence):
    directory.mkdir()
subprocess.run(["git", "init", "--quiet", str(workspace)], check=True)
image = subprocess.check_output(
    ["docker", "image", "inspect", WORKER_IMAGE, "--format", "{{.Id}}"], text=True
).strip()
executor = OpenCodeCommandExecutor(
    workspace, canonical, store, evidence, worker_image_id=image
)
try:
    results = []
    for command in (
        "git status --short",
        "git diff",
        "git diff --cached",
        "git config --get-all safe.directory",
    ):
        result = executor.execute(CommandRequest(command=command))
        results.append(
            {
                "command": command,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        if result.exit_code:
            raise RuntimeError("worker_git_trust_failed")
    if results[-1]["stdout"].strip() != "/draft":
        raise RuntimeError("worker_git_trust_scope_changed")
    print(json.dumps({"state": "passed", "image": image, "results": results}))
finally:
    executor.shutdown()
