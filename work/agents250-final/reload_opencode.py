"""Reload only the task-owned, confirmed-idle OpenCode API; no model call."""

import json
import os
from pathlib import Path
import subprocess


def main():
    root = Path("C:/CodeWorkspace/laomedo")
    e = root / "claude-review.local/agents-250-20261107"
    state = Path(json.loads((e / "runtime-path.json").read_text())["path"])
    launcher = state / "serve_opencode.py"
    for record in (state / "opencode/runs").glob("*/record.json"):
        if json.loads(record.read_text())["status"] not in {
            "completed",
            "cancelled",
            "failed",
            "timed_out",
            "interrupted",
        }:
            raise SystemExit("OpenCode not confirmed idle; left untouched")
    query = 'Get-NetTCPConnection -LocalPort 18817 -State Listen | ForEach-Object { Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)" } | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress'
    owner = json.loads(
        subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-Command", query], text=True
        )
    )
    if str(launcher) not in owner["CommandLine"]:
        raise SystemExit("OpenCode owner mismatch; left untouched")
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            f'Stop-Process -Id {int(owner["ProcessId"])}',
        ],
        check=True,
    )
    source = root / ".tools/agent-refactor-205"
    env = os.environ | {
        "PYTHONPATH": str(source / "src"),
        "LAOMEDO_AGENT_ACTIVITY_DB": str(state / "activity.db"),
    }
    with (state / "opencode.log").open("ab") as log:
        process = subprocess.Popen(
            [
                "C:/Users/Amadou/AppData/Local/Temp/lmi-be4oa1d0/Scripts/python.exe",
                str(launcher),
            ],
            cwd=source,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    records = json.loads((state / "processes.json").read_text())
    for record in records:
        if record["name"] == "opencode":
            record["pid"] = process.pid
    (state / "processes.json").write_text(json.dumps(records, indent=2))
    print(
        json.dumps(
            {
                "replaced_verified_idle_owner": owner["ProcessId"],
                "launcher": process.pid,
                "submitted_turns": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
