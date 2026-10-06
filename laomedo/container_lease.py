"""Exact-container lease supervision for a local runner process.

Superseded for runner launches by ``laomedo.lease_service``: EXP-93's frozen
whole-tree diagnostic showed this runner-spawned child supervisor dies with
the runner under ``taskkill /T /F``. The exact inspection and cleanup helpers
below remain shared. ``LeaseProcess``/``supervise`` are kept only so the
committed historical probes stay reproducible.

The supervisor is a separate process. It receives heartbeats over a private
pipe; an EOF or an expired heartbeat makes it stop only the labelled container
reserved by the durable run record. It never searches by a name prefix.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time


LEASE_SECONDS = 60
POST_LOSS_WATCH_SECONDS = 5
LABEL_RUN = "laomedo.run_id"
LABEL_TOKEN = "laomedo.launch_token"


def _detached_process_options() -> dict:
    """Keep the supervisor outside the runner's console/process group.

    Windows job containment may forbid breakaway. In that case Popen fails and
    the runner refuses to launch the container, rather than silently sharing
    the runner's fate.
    """
    if os.name == "nt":
        return {"creationflags": (subprocess.CREATE_NEW_PROCESS_GROUP |
                                  subprocess.CREATE_BREAKAWAY_FROM_JOB |
                                  subprocess.CREATE_NO_WINDOW)}
    return {"start_new_session": True}


class LeaseProcess:
    """Own a separately running supervisor and its heartbeat pipe."""

    def __init__(self, record_path: Path, name: str, run_id: str, token: str,
                 cancelled: threading.Event):
        self.stop_event = threading.Event()
        self.lost = threading.Event()
        self.ready = record_path.parent / ("lease-ready-" + token)
        self.result = record_path.parent / ("lease-result-" + token + ".json")
        self.log = (record_path.parent / ("lease-" + token + ".log")).open("a", encoding="utf-8")
        try:
            self.process = subprocess.Popen(
                [sys.executable, "-m", "laomedo.container_lease", str(record_path),
                 name, run_id, token, str(self.ready), str(self.result)],
                stdin=subprocess.PIPE, stdout=self.log, stderr=self.log,
                text=True, encoding="utf-8", **_detached_process_options())
        except Exception:
            self.log.close()
            raise
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not self.ready.exists():
            if self.process.poll() is not None:
                break
            time.sleep(.05)
        if not self.ready.exists() or self.ready.read_text(encoding="utf-8") != token:
            self.process.stdin.close()
            self.process.wait(timeout=5)
            self.log.close()
            raise RuntimeError("lease_supervisor_not_ready")

        def heartbeat() -> None:
            while not self.stop_event.wait(2):
                if self.process.poll() is not None:
                    self.lost.set()
                    cancelled.set()
                    break
                try:
                    self.process.stdin.write("HEARTBEAT\n")
                    self.process.stdin.flush()
                except (OSError, ValueError):
                    self.lost.set()
                    cancelled.set()
                    break

        self.thread = threading.Thread(target=heartbeat, daemon=True)
        self.thread.start()

    def finish(self, *, normal: bool) -> None:
        self.stop_event.set()
        self.thread.join(timeout=3)
        try:
            if self.process.poll() is None:
                if normal:
                    self.process.stdin.write("DONE\n")
                    self.process.stdin.flush()
                self.process.stdin.close()
                self.process.wait(timeout=15)
            report = (json.loads(self.result.read_text(encoding="utf-8"))
                      if self.result.exists() else {})
            expected = "done" if normal else "eof"
            if (self.process.returncode != 0 or self.lost.is_set() or
                    report.get("reason") != expected or
                    (normal and report.get("state") != "absent") or
                    (not normal and report.get("cleanup_verified") is not True)):
                raise RuntimeError("lease_supervisor_unverified")
        finally:
            self.log.close()


def inspect_exact(name: str, run_id: str, token: str) -> tuple[str, str | None]:
    """Return (absent|owned|conflict|unknown, container ID)."""
    try:
        result = subprocess.run(["docker", "inspect", name], capture_output=True,
                                text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return "unknown", None
    if result.returncode:
        if "No such object:" in result.stderr or "No such container:" in result.stderr:
            return "absent", None
        return "unknown", None
    try:
        entry = json.loads(result.stdout)[0]
        labels = entry["Config"]["Labels"] or {}
        if (entry["Name"].lstrip("/") != name or
                labels.get(LABEL_RUN) != run_id or
                labels.get(LABEL_TOKEN) != token):
            return "conflict", entry.get("Id")
        return "owned", entry["Id"]
    except (KeyError, IndexError, TypeError, ValueError):
        return "unknown", None


def cleanup_exact(name: str, run_id: str, token: str) -> tuple[bool, str]:
    """Stop only the exact labelled reservation, then prove it is absent."""
    state, container_id = inspect_exact(name, run_id, token)
    if state == "absent":
        return True, "absent"
    if state != "owned":
        return False, state
    try:
        result = subprocess.run(["docker", "rm", "-f", container_id],
                                capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False, "remove_unknown"
    after, _ = inspect_exact(name, run_id, token)
    if after == "absent":
        return True, "removed"
    return False, "remove_failed" if result.returncode else "still_present"


def cleanup_after_loss(name: str, run_id: str, token: str, *,
                       watch_seconds: float = POST_LOSS_WATCH_SECONDS) -> tuple[bool, str]:
    """Keep watching for a container created after the runner disappeared.

    Absence throughout the watch is *not* proof that a delayed Docker client
    cannot create it later. Report that case as unverified; never assert safe
    termination merely because the first inspection found nothing.
    """
    deadline = time.monotonic() + watch_seconds
    observed = False
    while True:
        state, _ = inspect_exact(name, run_id, token)
        if state in {"conflict", "unknown"}:
            return False, state
        if state == "owned":
            observed = True
            verified, detail = cleanup_exact(name, run_id, token)
            if not verified:
                return False, detail
        if time.monotonic() >= deadline:
            state, _ = inspect_exact(name, run_id, token)
            if state == "absent":
                return (True, "removed_after_loss") if observed else (False, "never_observed")
            return False, "late_" + state
        time.sleep(min(.1, max(0, deadline - time.monotonic())))


def supervise(record_path: Path, name: str, run_id: str, token: str,
              ready_path: Path, result_path: Path) -> int:
    events: queue.Queue[str] = queue.Queue()

    def read_pipe() -> None:
        for line in sys.stdin:
            events.put(line.strip())
        events.put("EOF")

    threading.Thread(target=read_pipe, daemon=True).start()
    record = json.loads(record_path.read_text(encoding="utf-8"))
    owner = record.get("container_ownership") or {}
    if (record.get("run_id") != run_id or owner.get("name") != name or
            owner.get("launch_token") != token):
        return 2
    ready_path.write_text(token, encoding="utf-8")
    deadline = time.monotonic() + LEASE_SECONDS
    while True:
        try:
            event = events.get(timeout=min(.5, max(.01, deadline - time.monotonic())))
        except queue.Empty:
            event = "EXPIRED" if time.monotonic() >= deadline else ""
        if event == "HEARTBEAT":
            deadline = time.monotonic() + LEASE_SECONDS
            continue
        if event == "DONE":
            # The parent must have stopped and verified the container first.
            state, _ = inspect_exact(name, run_id, token)
            result_path.write_text(json.dumps({"reason": "done", "state": state}) + "\n",
                                   encoding="utf-8")
            return 0 if state == "absent" else 3
        if event in {"EOF", "EXPIRED"}:
            verified, state = cleanup_after_loss(name, run_id, token)
            result_path.write_text(json.dumps({"reason": event.lower(),
                                               "cleanup_verified": verified,
                                               "state": state}) + "\n", encoding="utf-8")
            return 0 if verified else 4


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("record", type=Path)
    parser.add_argument("name")
    parser.add_argument("run_id")
    parser.add_argument("token")
    parser.add_argument("ready", type=Path)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    raise SystemExit(supervise(args.record, args.name, args.run_id, args.token,
                               args.ready, args.result))


if __name__ == "__main__":
    main()
