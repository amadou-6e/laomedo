"""Probe Codex's Linux command sandbox inside a credential-free Docker container."""

import json
from pathlib import Path
import subprocess
import tempfile


IMAGE = "laomedo-codex-boundary:0.159.2"
CONFIG = """\
default_permissions = "container-test"
approval_policy = "never"

[permissions.container-test.filesystem]
":root" = "read"
":workspace_roots" = "write"
"/home/runner/.codex/fixture-secret.txt" = "deny"

[permissions.container-test.network]
enabled = false
"""


def container_command(root: Path, shell_command: str, sandboxed: bool = True) -> list[str]:
    bootstrap = (
        "mkdir -p /home/runner/.codex && cp /config.toml /home/runner/.codex/config.toml "
        "&& printf FAKE-CREDENTIAL > /home/runner/.codex/fixture-secret.txt && "
    )
    runner = (
        bootstrap + "CODEX_HOME=/home/runner/.codex codex sandbox "
        "-P container-test -C /draft -- sh -c \"$1\""
        if sandboxed else bootstrap + "sh -c \"$1\""
    )
    return [
        "docker", "run", "--rm", "--pull=never", "--network", "none",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "64", "--memory", "512m", "--user", "10001:10001",
        "--mount", f"type=bind,source={root / 'draft'},target=/draft",
        "--mount", f"type=bind,source={root / 'canonical'},target=/canonical,readonly",
        "--mount", f"type=bind,source={root / 'store'},target=/store",
        "--mount", f"type=bind,source={root / 'config.toml'},target=/config.toml,readonly",
        "--workdir", "/draft", IMAGE, "sh", "-c", runner,
        "probe", shell_command,
    ]


def run_case(root: Path, shell_command: str, sandboxed: bool = True) -> dict:
    result = subprocess.run(container_command(root, shell_command, sandboxed),
                            capture_output=True, text=True, timeout=45,
                            encoding="utf-8", errors="replace")
    return {"exit_code": result.returncode,
            "stdout": result.stdout[:500],
            "stderr": result.stderr[:700].replace(str(root), "<scratch>")}


def main() -> None:
    workspace = Path(__file__).resolve().parents[3]
    scratch_parent = (workspace.parent / "probe-artifacts.local").resolve()
    if not scratch_parent.is_relative_to(workspace.parent.resolve()):
        raise ValueError("scratch_root_invalid")
    scratch_parent.mkdir(exist_ok=True)
    scratch = tempfile.TemporaryDirectory(prefix="laomedo-container-codex-",
                                          dir=scratch_parent,
                                          ignore_cleanup_errors=True)
    root = Path(scratch.name).resolve()
    if root == scratch_parent or not root.is_relative_to(scratch_parent):
        raise ValueError("scratch_path_invalid")
    report = {"image": IMAGE, "credential_used": False, "model_calls": 0,
              "network_mode": "none", "container_user": "10001:10001"}
    try:
        (root / "draft").mkdir()
        (root / "canonical").mkdir()
        (root / "store").mkdir()
        (root / "config.toml").write_text(CONFIG, encoding="utf-8")
        draft = root / "draft" / "SKILL.md"
        canonical = root / "canonical" / "protected.txt"
        store = root / "store" / "sentinel.txt"
        draft.write_text("DRAFT-ORIGINAL", encoding="utf-8")
        canonical.write_text("CANONICAL-ORIGINAL", encoding="utf-8")
        store.write_text("STORE-ORIGINAL", encoding="utf-8")
        report["store_positive_control"] = run_case(
            root, "printf CONTROL > /store/control.txt", sandboxed=False)
        report["secret_positive_control"] = run_case(
            root, "cat /home/runner/.codex/fixture-secret.txt", sandboxed=False)
        report["allowed"] = run_case(root,
            "printf DRAFT-EDITED > /draft/SKILL.md && cat /draft/SKILL.md")
        report["forbidden"] = run_case(root,
            "printf FORBIDDEN > /store/sentinel.txt")
        report["canonical_forbidden"] = run_case(root,
            "printf FORBIDDEN > /canonical/protected.txt")
        report["secret_denied"] = run_case(root,
            "cat /home/runner/.codex/fixture-secret.txt")
        report["host_draft_edited"] = draft.read_text(encoding="utf-8") == "DRAFT-EDITED"
        report["host_canonical_unchanged"] = (
            canonical.read_text(encoding="utf-8") == "CANONICAL-ORIGINAL")
        report["host_store_unchanged"] = store.read_text(encoding="utf-8") == "STORE-ORIGINAL"
        report["host_store_control_written"] = (
            (root / "store" / "control.txt").read_text(encoding="utf-8") == "CONTROL")
        report["boundary_passed"] = (
            report["store_positive_control"]["exit_code"] == 0
            and report["secret_positive_control"]["stdout"] == "FAKE-CREDENTIAL"
            and report["allowed"]["exit_code"] == 0
            and report["forbidden"]["exit_code"] != 0
            and report["canonical_forbidden"]["exit_code"] != 0
            and report["secret_denied"]["exit_code"] != 0
            and "FAKE-CREDENTIAL" not in report["secret_denied"]["stdout"]
            and report["host_draft_edited"]
            and report["host_canonical_unchanged"]
            and report["host_store_unchanged"]
            and report["host_store_control_written"])
    finally:
        scratch.cleanup()
        report["scratch_retained"] = root.exists()
        print(json.dumps(report, indent=2))
    if not report["boundary_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
