"""Credential-free native Codex sandbox filesystem boundary probe.

The synthetic draft and store are siblings in a disposable directory outside
Git. No model turn or credential is loaded. The probe does not change Codex
configuration or request Windows sandbox setup. Elevated mode may leave
protected setup files that require administrator rights to remove.
"""

import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "120"))
from _shared import AppServer, codex_version, construct_env


def execute(server, env: dict, draft: Path, target: Path, mode: str) -> dict:
    command = [str(Path(env["SystemRoot"]) / "System32" / "cmd.exe"),
               "/c", f"echo synthetic > {target}"]
    response = server.send("command/exec", {
        "command": command, "cwd": str(draft),
        "sandboxPolicy": ({"type": "workspaceWrite",
                           "writableRoots": [str(draft)], "networkAccess": True}
                          if mode == "workspaceWrite" else
                          {"type": "readOnly", "networkAccess": True}),
        "timeoutMs": 10000,
    }, timeout=20)
    return {"response": "result" in response,
            "exit_code": (response.get("result") or {}).get("exitCode"),
            "error_code": (response.get("error") or {}).get("code"),
            "error_message": (response.get("error") or {}).get("message", "")[:300],
            "stderr": (response.get("result") or {}).get("stderr", "")[:300],
            "file_written": target.is_file()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", required=True, type=Path)
    parser.add_argument("--windows-mode", choices=("default", "unelevated", "elevated"),
                        default="default")
    args = parser.parse_args()
    repo = Path.cwd().resolve()
    codex = args.codex.resolve(strict=True)
    summary = {"model_calls": 0, "credential_used": False,
               "config_file_changed": False, "sandbox_setup_requested": False,
               "network_access_for_synthetic_command": True,
               "requested_windows_mode": args.windows_mode}
    scratch_parent = (repo.parent / "probe-artifacts.local").resolve()
    if not scratch_parent.is_relative_to(repo.parent.resolve()):
        raise RuntimeError("scratch_parent_outside_workspace")
    if " " in str(scratch_parent):
        raise RuntimeError("scratch_path_with_spaces_unsupported")
    scratch_parent.mkdir(exist_ok=True)
    scratch = tempfile.TemporaryDirectory(prefix="laomedo-122-boundary-",
                                          dir=scratch_parent,
                                          ignore_cleanup_errors=True)
    state = Path(scratch.name).resolve()
    if not state.is_relative_to(scratch_parent):
        raise RuntimeError("scratch_outside_private_parent")
    server = None
    try:
        draft, store = state / "draft", state / "store"
        home, codex_home, private_temp = (
            draft / item for item in ("home", "codex-home", "tmp"))
        for folder in (draft, store, home, codex_home, private_temp):
            folder.mkdir()
        (store / "protected.txt").write_text("original\n", encoding="utf-8")
        env = construct_env(home, codex_home, draft, codex.parent)
        for folder in (draft / "appdata", draft / "localappdata"):
            folder.mkdir()
        env["TEMP"] = env["TMP"] = str(private_temp)
        summary["version"] = codex_version(codex, env).splitlines()[0]
        startup_args = (["-c", f'windows.sandbox="{args.windows_mode}"']
                        if args.windows_mode != "default" else [])
        server = AppServer(codex, draft, env, state, startup_args=startup_args)
        ok, _ = server.initialize()
        summary["initialized"] = ok
        if ok:
            config = server.send("config/read", {}, timeout=20)
            settings = (config.get("result") or {}).get("config") or {}
            windows = settings.get("windows") or {}
            summary["configured_windows_sandbox"] = windows.get("sandbox")
            summary["phase"] = "read_only"
            summary["read_only"] = execute(server, env, draft,
                                           draft / "readonly.txt", "readOnly")
            summary["phase"] = "draft_write"
            summary["draft_write"] = execute(server, env, draft,
                                              draft / "allowed.txt", "workspaceWrite")
            summary["phase"] = "sibling_store_write"
            summary["sibling_store_write"] = execute(
                server, env, draft, store / "outside.txt", "workspaceWrite")
            summary["phase"] = "complete"
            summary["protected_store_unchanged"] = (
                (store / "protected.txt").read_text(encoding="utf-8") == "original\n")
            summary["boundary_passed"] = (
                not summary["read_only"]["file_written"] and
                summary["draft_write"]["file_written"] and
                not summary["sibling_store_write"]["file_written"] and
                summary["protected_store_unchanged"])
    except Exception as exc:
        summary["error_class"] = type(exc).__name__
    finally:
        if server is not None:
            summary["server_close"] = server.close()
        scratch.cleanup()
        summary["protected_scratch_retained"] = state.exists()
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
