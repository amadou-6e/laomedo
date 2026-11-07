"""Exact-container lease supervision for a local runner process.

Superseded for runner launches by ``laomedo.host.leases.lease_service``: EXP-93's frozen
whole-tree diagnostic showed this runner-spawned child supervisor dies with
the runner under ``taskkill /T /F``. The exact inspection and cleanup helpers
below remain shared. ``LeaseProcess``/``supervise`` are kept only so the
committed historical probes stay reproducible.

The supervisor is a separate process. It receives heartbeats over a private
pipe; an EOF or an expired heartbeat makes it stop only the labelled container
reserved by the durable run record. It never searches by a name prefix."""

from __future__ import annotations

from pathlib import Path
import json
from laomedo.host.leases.utils import _detached_process_options
import subprocess
import sys
import threading
import time


class LeaseProcess:
    """Own a separately running supervisor and its heartbeat pipe."""

    def __init__(
        self,
        record_path: Path,
        name: str,
        run_id: str,
        token: str,
        cancelled: threading.Event,
    ):
        self.stop_event = threading.Event()
        self.lost = threading.Event()
        self.ready = record_path.parent / ("lease-ready-" + token)
        self.result = record_path.parent / ("lease-result-" + token + ".json")
        self.log = (record_path.parent / ("lease-" + token + ".log")).open(
            "a", encoding="utf-8"
        )
        try:
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "laomedo.host.leases.process_cli",
                    str(record_path),
                    name,
                    run_id,
                    token,
                    str(self.ready),
                    str(self.result),
                ],
                stdin=subprocess.PIPE,
                stdout=self.log,
                stderr=self.log,
                text=True,
                encoding="utf-8",
                **_detached_process_options(),
            )
        except Exception:
            self.log.close()
            raise
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not self.ready.exists():
            if self.process.poll() is not None:
                break
            time.sleep(0.05)
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
            report = (
                json.loads(self.result.read_text(encoding="utf-8"))
                if self.result.exists()
                else {}
            )
            expected = "done" if normal else "eof"
            if (
                self.process.returncode != 0
                or self.lost.is_set()
                or report.get("reason") != expected
                or (normal and report.get("state") != "absent")
                or (not normal and report.get("cleanup_verified") is not True)
            ):
                raise RuntimeError("lease_supervisor_unverified")
        finally:
            self.log.close()
