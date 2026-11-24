"""Independent Agent file-tree hashing and verified copying."""

from pathlib import Path
import hashlib
import os
import shutil
import stat
from laomedo.agents.errors import RunnerError
from .settings import (
    MAX_GIT_WORKSPACE_SNAPSHOT_BYTES,
    MAX_GIT_WORKSPACE_SNAPSHOT_ENTRIES,
)


def _hash_tree(path: Path, *, exclude_root_git: bool = False) -> str:
    """Hash regular files and directories, including empty directories."""
    if not path.is_dir() or path.is_symlink():
        raise RunnerError("invalid_workspace")
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
                raise RunnerError("unsafe_workspace_entry")
            if item.is_file():
                if item.stat().st_nlink != 1:
                    raise RunnerError("unsafe_workspace_entry")
                if exclude_root_git:
                    total_bytes += item.stat().st_size
                    if (
                        total_bytes > MAX_GIT_WORKSPACE_SNAPSHOT_BYTES
                        or len(files) + len(directories)
                        >= MAX_GIT_WORKSPACE_SNAPSHOT_ENTRIES
                    ):
                        raise RunnerError("git_workspace_snapshot_limit")
                files[item.relative_to(path).as_posix()] = item.read_bytes()
            else:
                directories.append(item.relative_to(path).as_posix())
                if (
                    exclude_root_git
                    and len(files) + len(directories)
                    > MAX_GIT_WORKSPACE_SNAPSHOT_ENTRIES
                ):
                    raise RunnerError("git_workspace_snapshot_limit")
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
        raise RunnerError("workspace_copy_mismatch")
    return expected
