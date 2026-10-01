"""Credential-free draft boundary check with a pinned Codex CLI binary.

Uses the direct `codex sandbox` command and an invocation-only named profile.
No model turn is submitted and no login material is copied or printed.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "120"))
from _shared import construct_env, inside_git_tree


def quote_ps(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", required=True, type=Path)
    parser.add_argument("--codex-home", required=True, type=Path)
    args = parser.parse_args()

    codex = args.codex.resolve(strict=True)
    if args.codex_home.is_symlink():
        raise ValueError("private_codex_home_symlink")
    codex_home = args.codex_home.resolve(strict=True)
    if not codex_home.is_dir() or inside_git_tree(codex_home):
        raise ValueError("private_codex_home_invalid")
    binary_hash = hashlib.sha256(codex.read_bytes()).hexdigest()
    workspace = Path(__file__).resolve().parents[3]
    scratch_parent = (workspace.parent / "probe-artifacts.local").resolve()
    if not scratch_parent.is_relative_to(workspace.parent.resolve()):
        raise ValueError("scratch_root_invalid")
    scratch_parent.mkdir(exist_ok=True)

    report = {"model_calls": 0, "credential_copied": False,
              "persistent_config_changed": False, "codex_sha256": binary_hash,
              "profile": "laomedo_ide_122", "windows_mode": "elevated"}
    scratch = tempfile.TemporaryDirectory(prefix="laomedo-ide-boundary-",
                                          dir=scratch_parent,
                                          ignore_cleanup_errors=True)
    root = Path(scratch.name).resolve()
    if root == scratch_parent or not root.is_relative_to(scratch_parent):
        raise ValueError("scratch_path_invalid")
    try:
        draft, store = root / "draft", root / "store"
        home, temp = draft / "home", draft / "tmp"
        for path in (draft, store, home, temp, draft / "appdata",
                     draft / "localappdata"):
            path.mkdir()
        inside, outside = draft / "allowed.txt", store / "protected.txt"
        inside.write_text("ORIGINAL", encoding="utf-8")
        outside.write_text("ORIGINAL", encoding="utf-8")
        script = draft / "boundary.ps1"
        script.write_text(
            "$ErrorActionPreference = 'Stop'\n"
            "try {\n"
            f"  Set-Content -LiteralPath {quote_ps(inside)} -Value 'ALLOWED' -NoNewline -ErrorAction Stop\n"
            "  Write-Output 'inside_write=ok'\n"
            f"  if ([System.IO.File]::ReadAllText({quote_ps(inside)}) -eq 'ALLOWED') {{ Write-Output 'inside_readback=ok' }}\n"
            "} catch { Write-Output ('inside_write=' + $_.Exception.GetType().Name) }\n"
            "try {\n"
            f"  Set-Content -LiteralPath {quote_ps(outside)} -Value 'CHANGED' -NoNewline -ErrorAction Stop\n"
            "  Write-Output 'outside_write=ok'\n"
            "} catch { Write-Output ('outside_write=' + $_.Exception.GetType().Name) }\n",
            encoding="utf-8")
        env = construct_env(home, codex_home, draft, codex.parent)
        env["TEMP"] = env["TMP"] = str(temp)
        powershell = Path(env["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        command = [
            str(codex), "sandbox", "-C", str(draft),
            "--permission-profile", "laomedo_ide_122",
            "--include-managed-config",
            "-c", "permissions.laomedo_ide_122={ filesystem = { ':root' = 'read', ':workspace_roots' = 'write' }, network = { enabled = false } }",
            "-c", 'windows.sandbox="elevated"',
            str(powershell), "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "RemoteSigned", "-File", str(script),
        ]
        try:
            completed = subprocess.run(command, cwd=draft, env=env, text=True,
                                       capture_output=True, timeout=90,
                                       encoding="utf-8", errors="replace")
            report["cli_exit_code"] = completed.returncode
            report["inside_command_ok"] = (
                "inside_write=ok" in completed.stdout and
                "inside_readback=ok" in completed.stdout)
            report["outside_command_denied"] = "outside_write=UnauthorizedAccessException" in completed.stdout
            report["stdout_excerpt"] = completed.stdout[:500].replace(str(root), "<scratch>")
            report["stderr_excerpt"] = (completed.stderr[:700]
                                        .replace(str(codex_home), "<private_codex_home>")
                                        .replace(str(Path.home()), "<user_home>")
                                        .replace(str(root), "<scratch>"))
            report["stderr_error_class"] = (
                "sandbox_setup_or_execution_error" if completed.returncode else None)
        except subprocess.TimeoutExpired:
            report["error_class"] = "TimeoutExpired"
        try:
            report["inside_verified"] = (inside.is_file() and
                                         inside.read_text(encoding="utf-8") == "ALLOWED")
        except PermissionError:
            report["inside_verified"] = False
            report["inside_host_read_denied"] = True
        report["outside_unchanged"] = outside.read_text(encoding="utf-8") == "ORIGINAL"
        report["boundary_passed"] = (
            report.get("cli_exit_code") == 0 and report.get("inside_command_ok")
            and report.get("outside_command_denied") and report["inside_verified"]
            and report["outside_unchanged"])
    finally:
        # The resolved target was checked above before recursive cleanup.
        scratch.cleanup()
        report["scratch_retained"] = root.exists()
        print(json.dumps(report, indent=2))
    if not report["boundary_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
