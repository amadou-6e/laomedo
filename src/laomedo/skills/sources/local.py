"""Admit local roots and read bounded skill files without registry or Git effects."""

from pathlib import Path
import os
import time
from laomedo.skills.inspection.settings import (
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_BUNDLE_BYTES,
)
from laomedo.skills.inspection.utils import _read_regular
from laomedo.skills.registry.files import is_link
from laomedo.skills.sources.bundle import validate_bundle_path
from laomedo.skills.sources.errors import SourceError
from laomedo.skills.sources.models import SkillSourceChoice
from laomedo.skills.sources.settings import MAX_ENTRIES
from laomedo.skills.sources.utils import excluded_parts, skill_name


class LocalSkillSource:
    """Own local source path admission, discovery and regular-file reading."""

    def __init__(self, allowed_roots=()):
        self.allowed_roots = [Path(path).absolute() for path in allowed_roots]

    def admit(self, path, *, require_exists=True):
        permitted = next(
            (
                root
                for root in self.allowed_roots
                if path == root or path.is_relative_to(root)
            ),
            None,
        )
        if permitted is None:
            raise SourceError("local_source_not_allowed")
        # Resolve only after checking every component, including the configured root.
        for component in [path, *path.parents]:
            if is_link(component):
                raise SourceError("local_source_unsafe")
        if (require_exists and not path.is_dir()) or not path.resolve().is_relative_to(
            permitted.resolve()
        ):
            raise SourceError("local_source_unavailable")
        return path

    def discover(self, root, deadline):
        result = []
        count = 0
        for parent, dirs, files in os.walk(root, followlinks=False):
            if time.monotonic() > deadline:
                raise SourceError("source_limit_exceeded")
            dirs[:] = [name for name in dirs if not excluded_parts((name,))]
            count += len(dirs) + len(files)
            if count > MAX_ENTRIES or len(Path(parent).relative_to(root).parts) > 16:
                raise SourceError("source_limit_exceeded")
            if any(is_link(Path(parent) / name) for name in dirs):
                raise SourceError("local_source_unsafe")
            if "SKILL.md" in files:
                relative = Path(parent).relative_to(root).as_posix()
                name = skill_name(
                    _read_regular(Path(parent) / "SKILL.md", MAX_FILE_BYTES),
                    Path(parent).name,
                )
                result.append(SkillSourceChoice.for_folder(name, relative))
                if len(result) > 128:
                    raise SourceError("source_limit_exceeded")
        return result

    def read(self, folder, deadline):
        if any(is_link(path) for path in [folder, *folder.parents]):
            raise SourceError("local_source_unsafe")
        if not (folder / "SKILL.md").exists():
            return None
        files = {}
        count = 0
        total = 0
        for parent, dirs, names in os.walk(folder, followlinks=False):
            if time.monotonic() > deadline:
                raise SourceError("source_limit_exceeded")
            dirs[:] = [name for name in dirs if not excluded_parts((name,))]
            count += len(dirs)
            if count > 128 or any(is_link(Path(parent) / name) for name in dirs):
                raise SourceError("local_source_unsafe")
            for name in names:
                if len(files) >= MAX_FILES:
                    raise SourceError("source_limit_exceeded")
                path = Path(parent) / name
                validate_bundle_path(path.relative_to(folder).as_posix())
                files[path.relative_to(folder).as_posix()] = _read_regular(
                    path, MAX_FILE_BYTES
                )
                total += len(files[path.relative_to(folder).as_posix()])
                if total > MAX_BUNDLE_BYTES:
                    raise SourceError("source_limit_exceeded")
        return files
