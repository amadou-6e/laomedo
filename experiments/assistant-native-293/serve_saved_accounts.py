"""Serve the owned chat preview through normal local profiles, without token injection."""

import json
import os
from pathlib import Path
import subprocess
import sys

workspace = Path("C:/CodeWorkspace/laomedo")
implementation = workspace / ".tools/worktrees/assistant-tools-293"
state = Path(os.environ["LOCALAPPDATA"]) / "Laomedo/acceptance/assistant-saved-293-01a1ba85"
metadata = workspace / ".tools/assistant-saved-login-live.json"
metadata.write_text(json.dumps({"state": str(state), "base": "http://127.0.0.1:55753", "implementation": str(implementation)}), encoding="utf-8")
command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(implementation / "tools/start_local_profiles.ps1"), "-Mode", "Serve", "-PythonExe", str(workspace / ".venv/Scripts/python.exe"), "-FrontendPath", str(workspace / ".tools/assistant-282-upstream/src/frontend/build"), "-RuntimeRoot", str(state), "-Port", "55753", "-LangflowSourceRoot", str(workspace / ".tools/assistant-282-upstream")]
raise SystemExit(subprocess.call(command))
