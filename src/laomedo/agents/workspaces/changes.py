"""Bounded, host-derived change projection from verified run snapshots."""

from difflib import unified_diff
from pathlib import Path
import hashlib
import os
import re
import stat
import unicodedata

from laomedo.agents.artifacts.errors import ArtifactError
from laomedo.agents.artifacts.utils import relative_path
from laomedo.agents.errors import RunnerError
from laomedo.agents.workspaces.settings import MAX_CHANGE_FILES
from laomedo.agents.workspaces.settings import MAX_CHANGE_FILE_BYTES
from laomedo.agents.workspaces.settings import MAX_CHANGE_PATCH_BYTES
from laomedo.agents.workspaces.settings import MAX_GIT_WORKSPACE_SNAPSHOT_BYTES
from laomedo.agents.workspaces.settings import MAX_GIT_WORKSPACE_SNAPSHOT_ENTRIES
from laomedo.agents.workspaces.utils import _hash_tree
from laomedo.agents.workspaces.utils import _raise_walk_error


def _files(root):
    """Enumerate regular paths after snapshot admission, excluding runtime metadata."""
    result, folders = {}, set()
    for parent, directories, names in os.walk(root, onerror=_raise_walk_error):
        relative = Path(parent).relative_to(root)
        if not relative.parts:
            directories[:] = [name for name in directories if name != ".git"]
        if relative.parts == (".agents",):
            directories[:] = [name for name in directories if name != "skills"]
        for name in directories:
            folder = (relative / name).as_posix()
            if folder != ".agents":
                folders.add(folder)
        for name in names:
            path = Path(parent) / name
            result[path.relative_to(root).as_posix()] = path
    return result, folders


def _file_digest(path):
    if path is None:
        return None
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.digest()


def _bounded_tree(root):
    """Refuse excessive trees before the existing in-memory snapshot hash runs."""
    total, count = 0, 0
    for parent, directories, names in os.walk(root, onerror=_raise_walk_error):
        count += len(directories) + len(names)
        if count > MAX_GIT_WORKSPACE_SNAPSHOT_ENTRIES:
            raise RunnerError("workspace_changes_too_large")
        for name in names:
            total += (Path(parent) / name).lstat().st_size
            if total > MAX_GIT_WORKSPACE_SNAPSHOT_BYTES:
                raise RunnerError("workspace_changes_too_large")


def verified_changes(
    canonical, post_run, *, source_hash, post_run_hash, imported_artifacts
):
    """Return exact snapshot-bound changes, or refuse incomplete representations."""
    canonical, post_run = Path(canonical), Path(post_run)
    try:
        if imported_artifacts != []:
            raise RunnerError("workspace_changes_imports_unsupported")
        _bounded_tree(canonical)
        _bounded_tree(post_run)
        if (
            _hash_tree(canonical) != source_hash
            or _hash_tree(post_run) != post_run_hash
        ):
            raise RunnerError("workspace_snapshot_mismatch")
        (before, before_dirs), (after, after_dirs) = _files(canonical), _files(post_run)
        if before_dirs != after_dirs:
            raise RunnerError("workspace_changes_directories_unsupported")
        if any(
            stat.S_IMODE(before[name].stat().st_mode)
            != stat.S_IMODE(after[name].stat().st_mode)
            for name in before.keys() & after.keys()
        ):
            raise RunnerError("workspace_changes_mode_unsupported")
        changed = [
            name
            for name in sorted(before.keys() | after.keys())
            if _file_digest(before.get(name)) != _file_digest(after.get(name))
        ]
        if len(changed) > MAX_CHANGE_FILES:
            raise RunnerError("workspace_changes_too_large")
        parts = []
        for name in changed:
            if any(
                unicodedata.category(char) in {"Cc", "Cf", "Zl", "Zp"} for char in name
            ):
                raise RunnerError("workspace_changes_protected")
            if any(
                part.casefold() in {"id_ecdsa", "id_dsa"}
                or part.casefold().startswith(("secrets.", "service-account"))
                or part.casefold().endswith((".pfx", ".ppk", ".jks", ".kdbx"))
                for part in name.split("/")
            ):
                raise RunnerError("workspace_changes_protected")
            try:
                relative_path(name)
            except ArtifactError:
                raise RunnerError("workspace_changes_protected") from None
            old, new = before.get(name), after.get(name)
            if any(
                path is not None and path.stat().st_size > MAX_CHANGE_FILE_BYTES
                for path in (old, new)
            ):
                raise RunnerError("workspace_changes_too_large")
            try:
                old_text = old.read_bytes().decode("utf-8") if old else ""
                new_text = new.read_bytes().decode("utf-8") if new else ""
            except UnicodeError:
                raise RunnerError("workspace_changes_binary") from None
            if "\x00" in old_text or "\x00" in new_text:
                raise RunnerError("workspace_changes_binary")
            parts.append(
                f"File: {name} ({'added' if old is None else 'deleted' if new is None else 'modified'})\n"
            )
            for line in unified_diff(
                re.findall(r"[^\n]*\n|[^\n]+", old_text),
                re.findall(r"[^\n]*\n|[^\n]+", new_text),
                fromfile="a/" + name,
                tofile="b/" + name,
            ):
                parts.append(
                    line
                    if line.endswith("\n")
                    else line + "\n\\ No newline at end of file\n"
                )
        patch = "".join(parts)
        if len(patch.encode("utf-8")) > MAX_CHANGE_PATCH_BYTES:
            raise RunnerError("workspace_changes_too_large")
        _bounded_tree(canonical)
        _bounded_tree(post_run)
        if (
            _hash_tree(canonical) != source_hash
            or _hash_tree(post_run) != post_run_hash
        ):
            raise RunnerError("workspace_snapshot_mismatch")
        return patch
    except OSError:
        raise RunnerError("workspace_access_failed") from None
