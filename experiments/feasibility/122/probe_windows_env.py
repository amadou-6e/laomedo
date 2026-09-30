"""Credential-free check for Windows cache paths in a private draft."""

import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "120"))
from _shared import AppServer, construct_env


codex = Path(sys.argv[1]).resolve(strict=True)
repo = Path(__file__).resolve().parents[3]
parent = repo.parent / "probe-artifacts.local"
if not parent.resolve().is_relative_to(repo.parent.resolve()):
    raise RuntimeError("scratch_parent_outside_workspace")
parent.mkdir(exist_ok=True)
reports = []
with tempfile.TemporaryDirectory(prefix="laomedo-122-env-", dir=parent,
                                 ignore_cleanup_errors=True) as scratch:
    root = Path(scratch)
    for name, with_system_drive in (("missing_systemdrive", False),
                                    ("present_systemdrive", True)):
        state = root / name
        draft = state / "draft"
        home = state / "home"
        codex_home = state / "codex-home"
        for path in (state, draft, home, codex_home, state / "appdata",
                     state / "localappdata", state / "tmp"):
            path.mkdir()
        (draft / "SKILL.md").write_text("synthetic\n", encoding="utf-8")
        env = construct_env(home, codex_home, state, codex.parent)
        env["TEMP"] = env["TMP"] = str(state / "tmp")
        if with_system_drive:
            env["SystemDrive"] = Path(env["SystemRoot"]).drive
        else:
            env.pop("SystemDrive")
        server = AppServer(codex, draft, env, state,
                           startup_args=["-c", 'windows.sandbox="elevated"'])
        try:
            ok, _ = server.initialize()
            response = server.send("command/exec", {
                "command": [str(Path(env["SystemRoot"]) / "System32" / "WindowsPowerShell" /
                                "v1.0" / "powershell.exe"), "-NoProfile", "-Command",
                            "Get-Content -Raw -LiteralPath SKILL.md"],
                "cwd": str(draft),
                "sandboxPolicy": {"type": "workspaceWrite",
                                  "writableRoots": [str(draft)],
                                  "networkAccess": False},
                "timeoutMs": 10000,
            }, timeout=25) if ok else {}
            reports.append({
                "variant": name, "initialized": ok,
                "command_response": "result" in response,
                "exit_code": (response.get("result") or {}).get("exitCode"),
                "error_code": (response.get("error") or {}).get("code"),
                "literal_systemdrive_tree": (draft / "%SystemDrive%").exists(),
                "draft_paths": sorted(str(path.relative_to(draft)) for path in draft.rglob("*")
                                      if path.is_file())[:8],
            })
        except Exception as exc:
            reports.append({"variant": name, "error_class": type(exc).__name__})
        finally:
            server.close()
print(json.dumps({"results": reports, "scratch_retained": root.exists()}, indent=2))
