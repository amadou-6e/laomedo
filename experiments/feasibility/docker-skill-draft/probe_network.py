"""Credential-free Docker and Codex Linux network boundary comparison."""

import json
from pathlib import Path
import subprocess
import tempfile


IMAGE = "laomedo-codex-boundary:0.159.2"


def main() -> None:
    workspace = Path(__file__).resolve().parents[3]
    scratch_parent = (workspace.parent / "probe-artifacts.local").resolve()
    if not scratch_parent.is_relative_to(workspace.parent.resolve()):
        raise ValueError("scratch_root_invalid")
    scratch_parent.mkdir(exist_ok=True)
    source = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="laomedo-docker-network-",
                                     dir=scratch_parent) as name:
        root = Path(name).resolve()
        if root == scratch_parent or not root.is_relative_to(scratch_parent):
            raise ValueError("scratch_path_invalid")
        draft = root / "draft"
        draft.mkdir()
        command = [
            "docker", "run", "--rm", "--pull=never", "--network", "bridge",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", "64", "--memory", "512m", "--user", "10001:10001",
            "--mount", f"type=bind,source={draft},target=/draft",
            "--mount", f"type=bind,source={source},target=/probe,readonly",
            "--mount", f"type=bind,source={source / 'network-config.toml'},target=/config.toml,readonly",
            "--workdir", "/draft", IMAGE, "node", "/probe/network-boundary.js",
        ]
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=60)
        try:
            report = json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            report = {"blocked": "no_json_report",
                      "error_excerpt": result.stderr[:500]}
        report["container_exit_code"] = result.returncode
        print(json.dumps(report, indent=2))
        if not report.get("boundary_passed"):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
