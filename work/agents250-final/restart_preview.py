"""Restart only the task-owned preview after adding a runner credential path."""

import json
import os
import subprocess
from pathlib import Path


def main():
    root = Path("C:/CodeWorkspace/laomedo")
    evidence = root / "claude-review.local/agents-250-20261107"
    state = Path(
        json.loads((evidence / "runtime-path.json").read_text(encoding="utf-8"))["path"]
    )
    source = root / ".tools/agent-refactor-205"
    app = state / "app.py"
    # Match the exact private launcher before stopping the listener; never kill
    # an arbitrary port owner or another preview.
    inspect = 'Get-NetTCPConnection -LocalPort 17863 -State Listen | ForEach-Object { Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)" } | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress'
    owner = json.loads(
        subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-Command", inspect], text=True
        )
    )
    if str(app) not in owner["CommandLine"]:
        raise SystemExit("Preview owner mismatch; left untouched.")
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            f'Stop-Process -Id {int(owner["ProcessId"])}',
        ],
        check=True,
    )
    frontend = Path(
        json.loads((evidence / "frontend-path.json").read_text(encoding="utf-8"))[
            "path"
        ]
    )
    env = os.environ | {
        "PYTHONPATH": str(source / "src"),
        "LAOMEDO_AGENT_ACTIVITY_DB": str(state / "activity.db"),
        "LANGFLOW_CONFIG_DIR": str(state / "langflow"),
        "LFX_CONFIG_DIR": str(state / "langflow"),
        "LANGFLOW_DATABASE_URL": "sqlite:///" + (state / "langflow/flow.db").as_posix(),
        "LANGFLOW_FRONTEND_PATH": str(frontend / "build"),
        "LANGFLOW_AUTO_LOGIN": "true",
        "DO_NOT_TRACK": "true",
        "LANGFLOW_COMPONENTS_PATH": str(source / "components"),
        "LAOMEDO_COMPONENT_DIR": str(source / "components/laomedo"),
        "LAOMEDO_SKILL_STORE": str(state / "registry"),
        "LAOMEDO_RUNNER_TOKEN_FILE": str(state / "codex/api-token"),
        "LAOMEDO_CODEX_RUNNER_TOKEN_FILE": str(state / "codex/api-token"),
        "LAOMEDO_CLAUDE_RUNNER_TOKEN_FILE": str(state / "claude/api-token"),
        "LAOMEDO_OPENCODE_RUNNER_TOKEN_FILE": str(state / "opencode/api-token"),
    }
    with (state / "app.log").open("ab") as output:
        process = subprocess.Popen(
            [
                "C:/Users/Amadou/AppData/Local/Temp/lmi-be4oa1d0/Scripts/python.exe",
                str(app),
            ],
            cwd=source,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    records = json.loads((state / "processes.json").read_text(encoding="utf-8"))
    for record in records:
        if record["name"] == "app":
            record["pid"] = process.pid
    (state / "processes.json").write_text(
        json.dumps(records, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "preview_pid": process.pid,
                "port": 17863,
                "stopped_verified_owner": owner["ProcessId"],
                "submitted_turns": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
