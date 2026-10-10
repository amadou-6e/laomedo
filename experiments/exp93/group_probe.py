"""One-shot Windows process-tree diagnostic for the EXP-93 amendment."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from uuid import uuid4

from laomedo.container_lease import LeaseProcess


OUTPUT = Path(__file__).with_name("group-observation.json")


def command_line(pid: int) -> str:
    response = subprocess.run(["powershell", "-NoProfile", "-Command",
        f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"],
        capture_output=True, text=True, timeout=10, check=True)
    return response.stdout.strip()


def child(root: Path) -> None:
    token = uuid4().hex
    run_id = uuid4().hex
    name = "laomedo-codex-probe-" + uuid4().hex
    record = root / "record.json"
    record.write_text(json.dumps({"run_id": run_id, "container_ownership": {
        "name": name, "launch_token": token}}), encoding="utf-8")
    lease = LeaseProcess(record, name, run_id, token, threading.Event())
    (root / "identities.json").write_text(json.dumps({"child_pid": os.getpid(),
        "supervisor_pid": lease.process.pid, "token": token}), encoding="utf-8")
    while True:
        time.sleep(1)


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "child":
        child(Path(sys.argv[2]).resolve())
        return
    if len(sys.argv) != 1 or os.name != "nt":
        raise SystemExit("Windows-only one-shot probe")
    if OUTPUT.exists():
        raise SystemExit("observation_exists_no_retry")
    root = Path(tempfile.mkdtemp(prefix="laomedo-exp93-group-"))
    process = subprocess.Popen([sys.executable, "-m", "experiments.exp93.group_probe",
                                "child", str(root)],
        cwd=Path(__file__).resolve().parents[2], stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
    killed = False
    try:
        until = time.monotonic() + 10
        while time.monotonic() < until and not (root / "identities.json").exists():
            if process.poll() is not None:
                raise RuntimeError("child_exited_before_ready")
            time.sleep(.05)
        identities = json.loads((root / "identities.json").read_text(encoding="utf-8"))
        if identities["child_pid"] != process.pid:
            raise RuntimeError("child_identity_mismatch")
        if ("experiments.exp93.group_probe" not in command_line(process.pid) or
                str(root) not in command_line(process.pid)):
            raise RuntimeError("child_command_mismatch")
        supervisor_pid = identities["supervisor_pid"]
        if ("laomedo.container_lease" not in command_line(supervisor_pid) or
                identities["token"] not in command_line(supervisor_pid)):
            raise RuntimeError("supervisor_command_mismatch")
        killed_at = time.monotonic()
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, text=True, timeout=10, check=True)
        killed = True
        result = root / ("lease-result-" + identities["token"] + ".json")
        until = time.monotonic() + 8
        while time.monotonic() < until and not result.exists():
            time.sleep(.1)
        report = json.loads(result.read_text(encoding="utf-8")) if result.exists() else None
        supervisor_command = command_line(supervisor_pid)
        still_running = ("laomedo.container_lease" in supervisor_command and
                         identities["token"] in supervisor_command)
        if still_running:
            subprocess.run(["taskkill", "/PID", str(supervisor_pid), "/F"],
                           capture_output=True, timeout=10, check=True)
        observed = {"schema_version": 1, "model_turns": 0,
            "kill_scope": "taskkill_exact_child_tree", "result_written": bool(report),
            "result_reason": report.get("reason") if report else None,
            "result_cleanup_verified": report.get("cleanup_verified") if report else None,
            "classification": ("survived_tree_kill" if report else
                               "inconclusive" if still_running else "killed_with_runner"),
            "elapsed_to_result_seconds": round(time.monotonic() - killed_at, 3)}
        OUTPUT.write_text(json.dumps(observed, indent=2) + "\n", encoding="utf-8",
                          newline="\n")
    finally:
        if not killed and process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, timeout=10)


if __name__ == "__main__":
    main()
