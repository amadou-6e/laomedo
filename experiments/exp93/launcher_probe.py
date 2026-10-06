"""One-shot short-lived-launcher parentage diagnostic on Windows."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from uuid import uuid4


OUTPUT = Path(__file__).with_name("launcher-observation.json")
MODULE = "experiments.exp93.launcher_probe"


def command_line(pid: int) -> str:
    response = subprocess.run(["powershell", "-NoProfile", "-Command",
        f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"],
        capture_output=True, text=True, timeout=10, check=True)
    return response.stdout.strip()


def launcher(root: Path, marker: str) -> None:
    flags = (subprocess.CREATE_NEW_PROCESS_GROUP |
             subprocess.CREATE_BREAKAWAY_FROM_JOB |
             subprocess.CREATE_NO_WINDOW)
    child = subprocess.Popen([sys.executable, "-m", MODULE, "supervisor", marker],
        cwd=Path(__file__).resolve().parents[2], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True, creationflags=flags)
    (root / "supervisor.json").write_text(json.dumps({"pid": child.pid}), encoding="utf-8")


def runner(root: Path, marker: str) -> None:
    spawned = subprocess.Popen([sys.executable, "-m", MODULE, "launcher",
                                str(root), marker],
        cwd=Path(__file__).resolve().parents[2], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    exit_code = spawned.wait(timeout=10)
    if exit_code:
        raise RuntimeError("launcher_failed")
    (root / "ready.json").write_text(json.dumps({"runner_pid": os.getpid(),
        "launcher_exited": True, "marker": marker}), encoding="utf-8")
    while True:
        time.sleep(1)


def main() -> None:
    if len(sys.argv) == 4 and sys.argv[1] == "launcher":
        launcher(Path(sys.argv[2]).resolve(), sys.argv[3])
        return
    if len(sys.argv) == 4 and sys.argv[1] == "runner":
        runner(Path(sys.argv[2]).resolve(), sys.argv[3])
        return
    if len(sys.argv) == 3 and sys.argv[1] == "supervisor":
        time.sleep(120)
        return
    if len(sys.argv) != 1 or os.name != "nt":
        raise SystemExit("Windows-only one-shot diagnostic")
    if OUTPUT.exists():
        raise SystemExit("observation_exists_no_retry")
    root = Path(tempfile.mkdtemp(prefix="laomedo-exp93-launcher-"))
    marker = "exp93-" + uuid4().hex
    child = subprocess.Popen([sys.executable, "-m", MODULE, "runner", str(root), marker],
        cwd=Path(__file__).resolve().parents[2], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    supervisor_pid = None
    killed_runner = False
    try:
        until = time.monotonic() + 10
        while time.monotonic() < until and not (root / "ready.json").exists():
            if child.poll() is not None:
                raise RuntimeError("runner_exited_before_ready")
            time.sleep(.05)
        ready = json.loads((root / "ready.json").read_text(encoding="utf-8"))
        supervisor_pid = json.loads((root / "supervisor.json").read_text(
            encoding="utf-8"))["pid"]
        if (ready["runner_pid"] != child.pid or not ready["launcher_exited"] or
                ready["marker"] != marker or
                MODULE + " runner" not in command_line(child.pid) or
                str(root) not in command_line(child.pid) or
                MODULE + " supervisor" not in command_line(supervisor_pid) or
                marker not in command_line(supervisor_pid)):
            raise RuntimeError("process_identity_mismatch")
        subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                       capture_output=True, text=True, timeout=10, check=True)
        killed_runner = True
        time.sleep(.5)
        still_alive = (MODULE + " supervisor" in command_line(supervisor_pid) and
                       marker in command_line(supervisor_pid))
        observed = {"schema_version": 1, "model_turns": 0,
            "kill_scope": "taskkill_exact_runner_tree",
            "launcher_exited_before_kill": True,
            "supervisor_alive_after_kill": still_alive,
            "classification": "survived_tree_kill" if still_alive else "killed_with_runner"}
        if still_alive:
            subprocess.run(["taskkill", "/PID", str(supervisor_pid), "/F"],
                           capture_output=True, timeout=10, check=True)
        OUTPUT.write_text(json.dumps(observed, indent=2) + "\n", encoding="utf-8",
                          newline="\n")
    finally:
        if not killed_runner and child.poll() is None:
            subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                           capture_output=True, timeout=10)
        if supervisor_pid is not None:
            cmd = command_line(supervisor_pid)
            if MODULE + " supervisor" in cmd and marker in cmd:
                subprocess.run(["taskkill", "/PID", str(supervisor_pid), "/F"],
                               capture_output=True, timeout=10)


if __name__ == "__main__":
    main()
