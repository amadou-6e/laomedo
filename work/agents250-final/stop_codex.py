"""Stop only this campaign's idle Codex API for actual recovery acceptance."""

import json
import subprocess
import sys
from pathlib import Path


def main():
    e = Path("C:/CodeWorkspace/laomedo/claude-review.local/agents-250-20261107")
    state = Path(
        json.loads((e / "runtime-path.json").read_text(encoding="utf-8"))["path"]
    )
    isolated = "--recovery" in sys.argv
    runner_state = state / "recovery-preview/runner" if isolated else state / "codex"
    port = 18825 if isolated else 18815
    for file in (runner_state / "runs").glob("*/record.json"):
        record = json.loads(file.read_text(encoding="utf-8"))
        if record["status"] in {"prepared", "running", "unknown"}:
            raise SystemExit("Native work is not confirmed idle; API left running.")
    query = (
        "Get-NetTCPConnection -LocalPort "
        + str(port)
        + ' -State Listen | ForEach-Object { Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)" } | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress'
    )
    owner = json.loads(
        subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-Command", query], text=True
        )
    )
    if (
        str(runner_state) not in owner["CommandLine"]
        or "laomedo.agents.agents.codex.cli" not in owner["CommandLine"]
    ):
        raise SystemExit("API ownership mismatch; left untouched.")
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            f'Stop-Process -Id {int(owner["ProcessId"])}',
        ],
        check=True,
    )
    result = {
        "stopped_verified_idle_api_pid": owner["ProcessId"],
        "port": port,
        "model_turns_submitted": 0,
    }
    (e / "recovery-stop.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
