"""Single-use, credential-free diagnostic; no model or native agent invocation."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import tempfile
import threading
import time

from laomedo.container_lease import inspect_exact, cleanup_exact

IDENTITY = "exp93-attached-client-d1-20261011"
IMAGE = "sha256:eceda79a349c46a8afd6fb271e92b979f872ca67cbdf228fde6dee0856481e78"


def command(name: str, nonce: str) -> list[str]:
    return ["docker", "run", "--rm", "-i", "--name", name,
            "--label", "laomedo.run_id=" + IDENTITY,
            "--label", "laomedo.launch_token=" + nonce,
            "--pull=never", "--network=none", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--pids-limit=32",
            "--memory=128m", "--user=10001:10001", IMAGE,
            "sh", "-c", "printf 'READY\\n'; while IFS= read -r line; do :; done"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True)
    args = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("windows_only")
    root = Path(tempfile.gettempdir()) / "laomedo-real-stage-campaign" / IDENTITY
    root.mkdir(parents=True, exist_ok=True)
    with (root / "single-use.claim").open("x", encoding="utf-8") as file:
        file.write(IDENTITY + "\n")
    nonce = secrets.token_hex(16)
    name = "laomedo-attached-d1-" + nonce[:12]
    row = {"identity": IDENTITY, "model_turns": 0, "provider_writes": 0,
           "source_sha": subprocess.check_output(
               ["git", "rev-parse", "HEAD"], text=True).strip(),
           "protocol_sha256": sha256(Path(__file__).with_name(
               "ATTACHED-CLIENT-DIAGNOSTIC-PROTOCOL.md").read_bytes()).hexdigest(),
           "image": IMAGE, "observations": [], "result": "incomplete"}
    process = None
    started = time.monotonic()
    try:
        if inspect_exact(name, IDENTITY, nonce)[0] != "absent":
            raise ValueError("name_not_absent")
        environment = {key: value for key, value in os.environ.items()
                       if not key.upper().startswith(("GH", "GITHUB", "ANTHROPIC", "OPENAI"))}
        process = subprocess.Popen(command(name, nonce), stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   text=True, env=environment)
        lines: queue.Queue[str] = queue.Queue()
        def read() -> None:
            for line in process.stdout:
                lines.put(line.strip())
        threading.Thread(target=read, daemon=True).start()
        if lines.get(timeout=30) != "READY":
            raise ValueError("fixture_not_ready")
        row["ready_at"] = time.monotonic()
        state, container_id = inspect_exact(name, IDENTITY, nonce)
        if state != "owned" or not container_id or process.poll() is not None:
            raise ValueError("owned_live_fixture_missing")
        row["container_id"] = container_id
        row["kill_started_at"] = time.monotonic()
        killed = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                capture_output=True, timeout=15)
        row["kill_completed_at"] = time.monotonic()
        row["kill_exit"] = killed.returncode
        if killed.returncode != 0:
            raise ValueError("kill_failed")
        for offset in (0, 1, 5, 10):
            remaining = row["kill_completed_at"] + offset - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            state, current_id = inspect_exact(name, IDENTITY, nonce)
            row["observations"].append({"offset": offset, "at": time.monotonic(),
                                        "state": state, "container_id": current_id})
            if state in {"unknown", "conflict"} or (
                    state == "owned" and current_id != container_id):
                raise ValueError("inspection_unverified_or_replaced")
        row["result"] = "observed"
    except Exception as error:
        row["error_class"] = type(error).__name__
        row["error_code"] = str(error) if isinstance(error, ValueError) else "diagnostic_error"
    finally:
        verified, detail = cleanup_exact(name, IDENTITY, nonce)
        row["cleanup"] = {"container_verified": verified, "state": detail}
        if process is not None:
            if process.poll() is None:
                process.kill()
            try:
                process.wait(timeout=15)
                row["cleanup"]["client_exited"] = True
            except subprocess.TimeoutExpired:
                row["cleanup"]["client_exited"] = False
            for stream in (process.stdin, process.stdout):
                stream.close()
        row["elapsed_seconds"] = time.monotonic() - started
        with (root / "observation.json").open("w", encoding="utf-8", newline="\n") as file:
            json.dump(row, file, sort_keys=True, indent=2)
            file.write("\n")
        print(json.dumps(row, sort_keys=True))
    if row["result"] != "observed" or not row["cleanup"]["container_verified"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
