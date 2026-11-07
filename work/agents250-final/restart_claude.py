"""Reload only the verified idle task Claude API with the reviewed source candidate."""

import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import Request, urlopen


def main():
    root = Path("C:/CodeWorkspace/laomedo")
    source = root / ".tools/agent-refactor-205"
    e = root / "claude-review.local/agents-250-20261107"
    state = Path(
        json.loads((e / "runtime-path.json").read_text(encoding="utf-8"))["path"]
    )
    for f in (state / "claude/runs").glob("*/record.json"):
        if json.loads(f.read_text(encoding="utf-8"))["status"] in {
            "prepared",
            "running",
            "unknown",
        }:
            raise SystemExit("Claude API not confirmed idle; retained.")
    query = 'Get-NetTCPConnection -LocalPort 18816 -State Listen | ForEach-Object { Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)" } | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress'
    owner = json.loads(
        subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-Command", query], text=True
        )
    )
    if (
        str(state / "claude") not in owner["CommandLine"]
        or "laomedo.agents.agents.claude.cli" not in owner["CommandLine"]
    ):
        raise SystemExit("Claude API ownership mismatch; retained.")
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            f'Stop-Process -Id {int(owner["ProcessId"])}',
        ],
        check=True,
    )
    env = os.environ | {
        "PYTHONPATH": str(source / "src"),
        "LAOMEDO_AGENT_ACTIVITY_DB": str(state / "activity.db"),
        "LAOMEDO_CLAUDE_MIRROR_HOST_LOGIN": "1",
        "LAOMEDO_CLAUDE_LOGIN_STATE_DIR": str(state / "claude-login"),
    }
    args = [
        "C:/Users/Amadou/AppData/Local/Temp/lmi-be4oa1d0/Scripts/python.exe",
        "-m",
        "laomedo.agents.agents.claude.cli",
        "--state",
        str(state / "claude"),
        "--skill-store",
        str(state / "registry"),
        "--source",
        str(state / "workspace/content"),
        "--lease-service",
        str(state / "lease"),
        "--port",
        "18816",
    ]
    with (state / "claude.log").open("ab") as log:
        process = subprocess.Popen(
            args,
            cwd=source,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    records = json.loads((state / "processes.json").read_text(encoding="utf-8"))
    for record in records:
        if record["name"] == "claude":
            record["pid"] = process.pid
    (state / "processes.json").write_text(
        json.dumps(records, indent=2), encoding="utf-8"
    )
    token = (state / "claude/api-token").read_text(encoding="utf-8").strip()
    start = time.monotonic()
    while time.monotonic() - start < 45:
        try:
            with urlopen(
                Request(
                    "http://127.0.0.1:18816/v1/models",
                    headers={"Authorization": "Bearer " + token},
                ),
                timeout=30,
            ) as response:
                catalog = json.load(response)
            if catalog.get("models"):
                break
        except OSError:
            time.sleep(0.5)
    else:
        raise SystemExit("Reloaded Claude catalog not ready; no model submitted.")
    print(
        json.dumps(
            {
                "replaced_verified_idle_pid": owner["ProcessId"],
                "pid": process.pid,
                "models_ready": True,
                "model_count": len(catalog["models"]),
                "submitted_turns": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
