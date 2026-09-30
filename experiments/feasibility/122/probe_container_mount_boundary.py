"""Credential-free Docker mount boundary probe for a disposable skill draft."""

import json
from pathlib import Path
import subprocess
import tempfile


IMAGE = "python:3.9-slim"
CONTAINER_CODE = r"""
import json
import os
from pathlib import Path
import sys

draft = Path('/draft/SKILL.md')
canonical = Path('/canonical/protected.txt')
original = canonical.read_text(encoding='utf-8')
draft.write_text('DRAFT-EDITED', encoding='utf-8')
try:
    canonical.write_text('FORBIDDEN', encoding='utf-8')
    denied = False
except OSError:
    denied = True
result = {
    'non_root': os.geteuid() != 0,
    'draft_readback': draft.read_text(encoding='utf-8') == 'DRAFT-EDITED',
    'canonical_write_denied': denied,
    'canonical_unchanged': canonical.read_text(encoding='utf-8') == original,
}
print(json.dumps(result))
sys.exit(0 if all(result.values()) else 1)
"""


def main() -> None:
    workspace = Path(__file__).resolve().parents[3]
    scratch_parent = (workspace.parent / "probe-artifacts.local").resolve()
    if not scratch_parent.is_relative_to(workspace.parent.resolve()):
        raise ValueError("scratch_root_invalid")
    scratch_parent.mkdir(exist_ok=True)
    scratch = tempfile.TemporaryDirectory(prefix="laomedo-container-boundary-",
                                          dir=scratch_parent,
                                          ignore_cleanup_errors=True)
    root = Path(scratch.name).resolve()
    if root == scratch_parent or not root.is_relative_to(scratch_parent):
        raise ValueError("scratch_path_invalid")
    report = {"model_calls": 0, "credential_used": False,
              "network_mode": "none", "image": IMAGE,
              "host_mounts": {"draft": "read_write", "canonical": "read_only"}}
    try:
        draft, canonical = root / "draft", root / "canonical"
        draft.mkdir()
        canonical.mkdir()
        (draft / "SKILL.md").write_text("DRAFT-ORIGINAL", encoding="utf-8")
        (canonical / "protected.txt").write_text("CANONICAL-ORIGINAL",
                                                  encoding="utf-8")
        command = [
            "docker", "run", "--rm", "--pull=never", "--network", "none",
            "--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,size=16m",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", "64", "--memory", "256m", "--user", "65532:65532",
            "--mount", f"type=bind,source={draft},target=/draft",
            "--mount", f"type=bind,source={canonical},target=/canonical,readonly",
            "--workdir", "/draft", IMAGE, "python", "-c", CONTAINER_CODE,
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True,
                                    timeout=45, encoding="utf-8", errors="replace")
            report["container_exit_code"] = result.returncode
            try:
                report["container_checks"] = json.loads(result.stdout.strip())
            except json.JSONDecodeError:
                report["container_checks"] = None
            report["docker_error_class"] = (
                "container_run_failed" if result.returncode else None)
            report["stderr_excerpt"] = result.stderr[:350].replace(str(root), "<scratch>")
        except subprocess.TimeoutExpired:
            report["docker_error_class"] = "TimeoutExpired"
        report["host_draft_edited"] = ((draft / "SKILL.md").read_text(encoding="utf-8")
                                       == "DRAFT-EDITED")
        report["host_canonical_unchanged"] = (
            (canonical / "protected.txt").read_text(encoding="utf-8")
            == "CANONICAL-ORIGINAL")
        report["boundary_passed"] = (
            report.get("container_exit_code") == 0 and
            bool(report.get("container_checks")) and
            all(report["container_checks"].values()) and
            report["host_draft_edited"] and report["host_canonical_unchanged"])
    finally:
        # The resolved target was checked above before recursive cleanup.
        scratch.cleanup()
        report["scratch_retained"] = root.exists()
        print(json.dumps(report, indent=2))
    if not report["boundary_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
