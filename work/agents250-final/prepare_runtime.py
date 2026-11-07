"""Prepare private real-provider inputs; never read or print login material."""

import json
import subprocess
import tempfile
from pathlib import Path


def main():
    root = Path("C:/CodeWorkspace/laomedo")
    evidence = root / "claude-review.local/agents-250-20261107"
    pointer = evidence / "runtime-path.json"
    if pointer.exists():
        print("Existing task-owned runtime retained; no reset or new model dispatch.")
        return
    state = Path(tempfile.mkdtemp(prefix="laomedo-agents250-"))
    content = state / "workspace/content"
    content.mkdir(parents=True)
    source = root / ".tools/agent-refactor-205"
    readme = subprocess.check_output(
        ["git", "-C", str(source), "show", "HEAD:README.md"]
    )
    (content / "README.md").write_bytes(readme)
    subprocess.run(
        ["git", "init", str(state / "workspace")], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(state / "workspace"), "add", "content/README.md"], check=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(state / "workspace"),
            "-c",
            "user.name=Laomedo validation",
            "-c",
            "user.email=validation@localhost",
            "commit",
            "-m",
            "Retain actual project README for read-only provider validation",
        ],
        check=True,
        capture_output=True,
    )
    for directory in ["registry", "lease", "codex", "claude", "opencode"]:
        (state / directory).mkdir()
    pointer.write_text(json.dumps({"path": str(state)}, indent=2), encoding="utf-8")
    print(
        "Prepared real tracked README in a private files-only workspace. No credential copy or model dispatch."
    )


if __name__ == "__main__":
    main()
