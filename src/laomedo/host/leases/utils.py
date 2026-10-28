"""Inspect exact reservations, reconcile cleanup and persist lease state."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from pathlib import Path
import json
import laomedo.host.leases.settings as _leases_settings
import laomedo.host.leases.models as _leases_models
import laomedo.host.mediation.errors as _mediation_errors
import laomedo.host.mediation.store as _mediation_store
import os
import queue
import secrets
import subprocess
import sys
import threading
import time


def _detached_process_options() -> dict:
    """Keep the supervisor outside the runner's console/process group.

    Windows job containment may forbid breakaway. In that case Popen fails and
    the runner refuses to launch the container, rather than silently sharing
    the runner's fate.
    """
    if os.name == "nt":
        return {
            "creationflags": (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_BREAKAWAY_FROM_JOB
                | subprocess.CREATE_NO_WINDOW
            )
        }
    return {"start_new_session": True}


def inspect_exact(identity: _leases_models.ContainerIdentity) -> tuple[str, str | None]:
    """Inspect on the original endpoint; legacy missing endpoint stays unknown."""
    try:
        with identity.client() as client:
            observation = client.containers.watch(identity.reservation()).inspect()
            return observation.state, observation.identity.id if observation.identity else None
    except (ImportError, OSError, ValueError, RuntimeError):
        return "unknown", None


def cleanup_exact(identity: _leases_models.ContainerIdentity) -> tuple[bool, str]:
    """Delegate exact removal and confirmation to the endpoint-bound runtime."""
    return cleanup_after_loss(identity, watch_seconds=0)


def cleanup_after_loss(
    identity: _leases_models.ContainerIdentity,
    *,
    watch_seconds: float = _leases_settings.POST_LOSS_WATCH_SECONDS,
) -> tuple[bool, str]:
    """Revoke in Laomedo first; delegate Docker's delayed-create watch to runtime."""
    try:
        with identity.client() as client:
            result = client.containers.watch(identity.reservation()).cleanup(
                watch_seconds=watch_seconds
            )
            return result.verified, result.detail
    except (ImportError, OSError, ValueError, RuntimeError):
        return False, "unknown"


def supervise(
    record_path: Path,
    name: str,
    run_id: str,
    token: str,
    ready_path: Path,
    result_path: Path,
) -> int:
    events: queue.Queue[str] = queue.Queue()

    def read_pipe() -> None:
        for line in sys.stdin:
            events.put(line.strip())
        events.put("EOF")

    threading.Thread(target=read_pipe, daemon=True).start()
    record = json.loads(record_path.read_text(encoding="utf-8"))
    owner = record.get("container_ownership") or {}
    if (
        record.get("run_id") != run_id
        or owner.get("name") != name
        or owner.get("launch_token") != token
    ):
        return 2
    ready_path.write_text(token, encoding="utf-8")
    deadline = time.monotonic() + _leases_settings.LEASE_SECONDS
    while True:
        try:
            event = events.get(timeout=min(0.5, max(0.01, deadline - time.monotonic())))
        except queue.Empty:
            event = "EXPIRED" if time.monotonic() >= deadline else ""
        if event == "HEARTBEAT":
            deadline = time.monotonic() + _leases_settings.LEASE_SECONDS
            continue
        if event == "DONE":
            # The parent must have stopped and verified the container first.
            state, _ = inspect_exact(
                _leases_models.ContainerIdentity(
                    name=name,
                    run_id=run_id,
                    token=token,
                    docker_endpoint=owner.get("docker_endpoint"),
                )
            )
            result_path.write_text(
                json.dumps({"reason": "done", "state": state}) + "\n", encoding="utf-8"
            )
            return 0 if state == "absent" else 3
        if event in {"EOF", "EXPIRED"}:
            verified, state = cleanup_after_loss(
                _leases_models.ContainerIdentity(
                    name=name,
                    run_id=run_id,
                    token=token,
                    docker_endpoint=owner.get("docker_endpoint"),
                )
            )
            result_path.write_text(
                json.dumps(
                    {
                        "reason": event.lower(),
                        "cleanup_verified": verified,
                        "state": state,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            return 0 if verified else 4


def _atomic_text(path: Path, value: str) -> None:
    pending = path.with_name(path.name + ".pending-" + secrets.token_hex(4))
    try:
        pending.write_text(value, encoding="utf-8")
        for attempt in range(20):
            try:
                os.replace(pending, path)
                return
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.01)
    finally:
        pending.unlink(missing_ok=True)


def _write_json(path: Path, value: dict) -> None:
    _atomic_text(path, json.dumps(value, sort_keys=True) + "\n")


def _write_float(path: Path, value: float) -> None:
    """Publish a heartbeat without exposing a truncated value to readers."""
    _atomic_text(path, repr(value))


def _read_json(path: Path) -> dict | None:
    for attempt in range(5):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except (PermissionError, FileNotFoundError):
            if attempt < 4:
                time.sleep(0.01)
        except (OSError, ValueError):
            return None
    return None


def _read_float(path: Path) -> float | None:
    for attempt in range(5):
        try:
            return float(path.read_text(encoding="utf-8").strip())
        except (PermissionError, FileNotFoundError):
            if attempt < 4:
                time.sleep(0.01)
        except (OSError, ValueError):
            return None
    return None
