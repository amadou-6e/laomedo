"""Provider-neutral private state and workspace helpers."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID
from uuid import uuid4
import json
from laomedo.agents.errors import RunnerError
import os
import time


def _git_tree(path: Path) -> bool:
    return any((parent / ".git").exists() for parent in (path, *path.parents))


def _private(path: Path) -> Path:
    path = path.expanduser().resolve()
    if _git_tree(path) or path.is_symlink():
        raise RunnerError("private_state_must_be_outside_git")
    return path


def _json(path: Path, value: dict) -> None:
    pending = path.with_name(path.name + ".pending-" + uuid4().hex)
    pending.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    try:
        # Windows can deny replacement while a concurrent poll has the old
        # record open. Keep the write atomic; only retry that transient lock.
        for attempt in range(20):
            try:
                os.replace(pending, path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.01)
    finally:
        pending.unlink(missing_ok=True)


def _read(path: Path) -> dict:
    # A concurrent atomic replacement can briefly deny a Windows reader.
    for attempt in range(5):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.01)
    if not isinstance(value, dict):
        raise RunnerError("invalid_record")
    return value


def _id(value: str) -> str:
    if str(UUID(value)) != value:
        raise RunnerError("invalid_run_id")
    return value
