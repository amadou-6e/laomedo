"""Provider-neutral private state and workspace helpers."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID
from uuid import uuid4
import hashlib
import json
import laomedo.agents.runtime.settings as _runtime_settings
import laomedo.agents.runtime.errors as _runtime_errors
import os
import shutil
import stat
import time


def _git_tree(path: Path) -> bool:
    return any((parent / ".git").exists() for parent in (path, *path.parents))


def _private(path: Path) -> Path:
    path = path.expanduser().resolve()
    if _git_tree(path) or path.is_symlink():
        raise _runtime_errors.RunnerError("private_state_must_be_outside_git")
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
        raise _runtime_errors.RunnerError("invalid_record")
    return value


def _hash_tree(path: Path, *, exclude_root_git: bool = False) -> str:
    """Hash regular files and directories, including empty directories."""
    if not path.is_dir() or path.is_symlink():
        raise _runtime_errors.RunnerError("invalid_workspace")
    files = {}
    directories = []
    total_bytes = 0
    for parent, dirs, names in os.walk(path, followlinks=False):
        if exclude_root_git and Path(parent) == path:
            dirs[:] = [name for name in dirs if name != ".git"]
            names = [name for name in names if name != ".git"]
        for name in dirs + names:
            item = Path(parent) / name
            if (
                item.is_symlink()
                or getattr(item.lstat(), "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
                or not (item.is_dir() or item.is_file())
            ):
                raise _runtime_errors.RunnerError("unsafe_workspace_entry")
            if item.is_file():
                if item.stat().st_nlink != 1:
                    raise _runtime_errors.RunnerError("unsafe_workspace_entry")
                if exclude_root_git:
                    total_bytes += item.stat().st_size
                    if (
                        total_bytes
                        > _runtime_settings.MAX_GIT_WORKSPACE_SNAPSHOT_BYTES
                        or len(files) + len(directories)
                        >= _runtime_settings.MAX_GIT_WORKSPACE_SNAPSHOT_ENTRIES
                    ):
                        raise _runtime_errors.RunnerError(
                            "git_workspace_snapshot_limit"
                        )
                files[item.relative_to(path).as_posix()] = item.read_bytes()
            else:
                directories.append(item.relative_to(path).as_posix())
                if (
                    exclude_root_git
                    and len(files) + len(directories)
                    > _runtime_settings.MAX_GIT_WORKSPACE_SNAPSHOT_ENTRIES
                ):
                    raise _runtime_errors.RunnerError("git_workspace_snapshot_limit")
    digest = hashlib.sha256()
    for relative in sorted(directories):
        encoded = relative.encode("utf-8")
        digest.update(b"D")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    for relative, data in sorted(files.items()):
        encoded = relative.encode("utf-8")
        digest.update(b"F")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return "sha256:" + digest.hexdigest()


def _copy_tree(source: Path, target: Path, *, exclude_root_git: bool = False) -> str:
    expected = _hash_tree(source, exclude_root_git=exclude_root_git)
    ignore = (
        (
            lambda parent, names: {
                name for name in names if Path(parent) == source and name == ".git"
            }
        )
        if exclude_root_git
        else None
    )
    shutil.copytree(source, target, ignore=ignore)
    if _hash_tree(target) != expected:
        raise _runtime_errors.RunnerError("workspace_copy_mismatch")
    return expected


def _id(value: str) -> str:
    if str(UUID(value)) != value:
        raise _runtime_errors.RunnerError("invalid_run_id")
    return value




def terminal_record(record):
    """Stable terminal states shared by graph clients and asynchronous runner polling."""
    return (record.get("status") in {"completed", "cancelled", "failed", "timeout", "interrupted"}
            or record.get("status") == "unknown" and record.get("attempt_finished") is True)
