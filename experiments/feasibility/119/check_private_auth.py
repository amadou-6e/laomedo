"""Check a private Codex profile's auth mode without printing credentials."""

import argparse
import json
import os
from pathlib import Path
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()

    state = args.state_dir.resolve(strict=True)
    private_home = state / "home"
    codex_home = state / "codex-home"
    if not private_home.is_dir() or not codex_home.is_dir():
        raise ValueError("private profile directories are missing")
    if not (codex_home / "auth.json").is_file():
        raise ValueError("private file-backed auth is missing")

    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    codex = args.codex.resolve(strict=True)
    env = {
        "HOME": str(private_home),
        "USERPROFILE": str(private_home),
        "HOMEDRIVE": private_home.drive,
        "HOMEPATH": str(private_home)[len(private_home.drive) :],
        "CODEX_HOME": str(codex_home),
        "APPDATA": str(state / "appdata"),
        "LOCALAPPDATA": str(state / "localappdata"),
        "TEMP": str(state),
        "TMP": str(state),
        "SystemRoot": system_root,
        "WINDIR": system_root,
        "PATH": os.pathsep.join([str(codex.parent), str(Path(system_root) / "System32")]),
    }
    process = subprocess.run(
        [str(codex), "login", "status"],
        cwd=state,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        encoding="utf-8",
        errors="replace",
    )
    output = (process.stdout + process.stderr).lower()
    print(
        json.dumps(
            {
                "status_exit_code": process.returncode,
                "chatgpt_login_reported": process.returncode == 0 and "chatgpt" in output,
                "api_key_login_reported": process.returncode == 0 and "api key" in output,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
