"""Durable, credential-free ownership and orphan cleanup for Git stages."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import subprocess

from .bundle_ingest import _durable_json, _redirected


@contextmanager
def stage_lock(attempt: Path):
    """OS lock proves a cooperating stage is alive; PID reuse is irrelevant."""
    path = attempt / "container.lock"
    if path.exists() and _redirected(path):
        raise ValueError("stage_lock_redirected")
    with path.open("a+b") as lock:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
            os.fsync(lock.fileno())
        lock.seek(0)
        acquired = False
        try:
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError:
                pass
            yield acquired
        finally:
            if acquired:
                lock.seek(0)
                if os.name == "nt":
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def reserve_container(attempt: Path, owner: dict):
    """Persist exact identity before create; never reuse an old reservation."""
    path = attempt / "container-owner.json"
    with path.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(owner, file, sort_keys=True)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())


def _inspect(owner, docker):
    result = docker(["docker", "inspect", owner["name"]], 10)
    if result.returncode:
        if "No such object:" in result.stderr or "No such container:" in result.stderr:
            return "absent", None
        return "unknown", None
    value = json.loads(result.stdout)
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        return "unknown", None
    entry = value[0]
    config = entry.get("Config")
    if not isinstance(config, dict):
        return "unknown", None
    labels = config.get("Labels") or {}
    if not isinstance(labels, dict) or not isinstance(entry.get("Id"), str):
        return "unknown", None
    if (entry.get("Name") != "/" + owner["name"] or
            labels.get("laomedo.bundle-stage") != owner["name"] or
            labels.get("laomedo.bundle-stage-token") != owner["token"] or
            entry.get("Image") != owner["image_id"] or
            not re.fullmatch(r"[0-9a-f]{64}", entry.get("Id", ""))):
        return "conflict", None
    return "owned", entry["Id"]


def reconcile_orphan(attempt: Path, *, docker):
    """Lookup/remove only after the stage's OS lock is free; never dispatch."""
    path = attempt / "container-owner.json"
    if not path.exists():
        return None
    if _redirected(path) or path.stat().st_size > 16384:
        return {"cleanup_verified": False, "detail": "owner_invalid"}
    try:
        owner = json.loads(path.read_bytes())
        if (not isinstance(owner, dict) or
                not re.fullmatch(r"laomedo-bundle-stage-[0-9a-f]{16}", owner.get("name", "")) or
                not re.fullmatch(r"[0-9a-f]{64}", owner.get("token", "")) or
                not re.fullmatch(r"sha256:[0-9a-f]{64}", owner.get("image_id", ""))):
            raise ValueError("owner_invalid")
        with stage_lock(attempt) as acquired:
            if not acquired:
                return None
            state, container_id = _inspect(owner, docker)
            if state == "owned":
                # Recheck before ID-only removal. A same-name replacement is
                # never selected as a cleanup target by prefix or name alone.
                again, current_id = _inspect(owner, docker)
                if again != "owned" or current_id != container_id:
                    state = "changed"
                else:
                    removed = docker(["docker", "rm", "--force", container_id], 15)
                    after, _ = _inspect(owner, docker)
                    if removed.returncode == 0 and after == "absent":
                        report = {"cleanup_verified": True, "detail": "removed"}
                        _durable_json(attempt / "orphan-cleanup.json", report)
                        return report
                    state = "remove_unknown"
            # Initial absence is not proof a previously dispatched Docker
            # create client cannot produce a late container. Future scans
            # keep looking; they never create/start anything.
            report = {"cleanup_verified": False, "detail": state}
            _durable_json(attempt / "orphan-cleanup.json", report)
            return report
    except (OSError, ValueError, TypeError, KeyError, IndexError,
            subprocess.TimeoutExpired):
        return {"cleanup_verified": False, "detail": "unknown"}
