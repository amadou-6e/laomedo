"""Verify packaged source and defining imports outside the checkout."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    root = Path("C:/CodeWorkspace/laomedo")
    source = root / ".tools/agent-refactor-205"
    e = root / "claude-review.local/agents-250-20261107"
    target = Path(tempfile.mkdtemp(prefix="laomedo-agents250-wheel-"))
    with (e / "wheel-build.log").open("wb") as log:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                str(source),
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                str(target / "wheels"),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
        wheel = next((target / "wheels").glob("*.whl"))
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                str(wheel),
                "--no-deps",
                "--target",
                str(target / "site"),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    files = [
        p
        for p in (source / "src/laomedo").rglob("*.py")
        if "__pycache__" not in p.parts
    ]
    missing = []
    changed = []
    for file in files:
        packaged = target / "site" / file.relative_to(source / "src")
        if not packaged.is_file():
            missing.append(file.relative_to(source).as_posix())
        elif packaged.read_bytes() != file.read_bytes():
            changed.append(file.relative_to(source).as_posix())
    code = (
        """import json,laomedo
from pathlib import Path
from laomedo.agents.agents.base.agent import BaseAgent
from laomedo.agents.agents.codex.agent import CodexAgent
from laomedo.agents.agents.claude.agent import ClaudeAgent
from laomedo.agents.agents.opencode.agent import OpenCodeAgent
from laomedo.agents.interface.bridge import HttpAgentBridge
from laomedo.host.runner.http.server import RunnerServer
expected=Path("""
        + repr(str(target / "site"))
        + """).resolve()
origin=Path(laomedo.__file__).resolve()
assert origin.is_relative_to(expected),origin
assert all(issubclass(provider,BaseAgent) for provider in [CodexAgent,ClaudeAgent,OpenCodeAgent])
import langflow
from laomedo.agents.interface.langflow.component import AgentComponent
reference=next(field for field in AgentComponent.inputs if field.name=='run_reference')
assert reference.show is True
print(json.dumps({'import_origin_outside_checkout':True,'provider_inheritance':True,'graph_adapter':True,'refresh_metadata_preserves_run_target':True}))
"""
    )
    out = subprocess.check_output(
        [sys.executable, "-c", code],
        cwd=target,
        env=os.environ | {"PYTHONPATH": str(target / "site")},
        text=True,
    )
    fact = json.loads(out.strip().splitlines()[-1])
    result = {
        "head": subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
        ).strip(),
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "source_files_checked": len(files),
        "missing": missing,
        "changed": changed,
        "smoke": fact,
        "scope": "Package/source parity and real imports only; not model or browser acceptance.",
    }
    (e / "wheel-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    if missing or changed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
