"""Bounded, read-only inspection of an exact immutable registry revision."""

from __future__ import annotations

from laomedo.skills.registry.files import is_link
from laomedo.skills.registry.hashing import file_hashes
from laomedo.skills.registry.hashing import tree_hash

from pathlib import Path
import base64
import json
import laomedo.skills.inspection.settings as _inspection_settings
import laomedo.skills.inspection.errors as _inspection_errors
import laomedo.skills.registry.settings as _registry_settings
import laomedo.skills.registry.errors as _registry_errors
import os
import stat


def _read_regular(path: Path, limit: int) -> bytes:
    metadata = path.lstat()
    if is_link(path) or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise _inspection_errors.InspectionError("skill_revision_unsafe")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        current = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(current.st_mode)
            or current.st_nlink != 1
            or (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino)
        ):
            raise _inspection_errors.InspectionError("skill_revision_unsafe")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise _inspection_errors.InspectionError("skill_revision_too_large")
    return data


def inspect_skill(
    root: Path, skill_id: str, revision_id: str, *, include_images: bool = False
) -> dict:
    if not isinstance(skill_id, str) or not _registry_settings.NAME.fullmatch(skill_id):
        raise _inspection_errors.InspectionError("invalid_skill_id")
    if not isinstance(revision_id, str) or not _registry_settings.HASH.fullmatch(
        revision_id
    ):
        raise _inspection_errors.InspectionError("immutable_skill_revision_required")
    # Inspect without constructing a mutable store or creating draft folders.
    root = Path(root).absolute()
    folder = root / "skills" / skill_id / "revisions" / revision_id[7:]
    try:
        for path in (
            root,
            root / "skills",
            folder.parent.parent,
            folder.parent,
            folder,
        ):
            if is_link(path) or not path.is_dir():
                raise _inspection_errors.InspectionError("skill_revision_unavailable")
        record = json.loads(_read_regular(folder / "record.json", 64 * 1024))
        if not isinstance(record, dict):
            raise _inspection_errors.InspectionError("skill_revision_unavailable")
        bundle = folder / "bundle"
        if is_link(bundle) or not bundle.is_dir():
            raise _inspection_errors.InspectionError("skill_revision_unsafe")
        contents = {}
        total = 0
        directory_count = 0
        for parent, directories, names in os.walk(bundle, followlinks=False):
            directory_count += len(directories)
            if (
                directory_count > _inspection_settings.MAX_DIRECTORIES
                or len(Path(parent).relative_to(bundle).parts)
                > _inspection_settings.MAX_DEPTH
            ):
                raise _inspection_errors.InspectionError("skill_revision_too_large")
            for name in directories:
                if is_link(Path(parent) / name):
                    raise _inspection_errors.InspectionError("skill_revision_unsafe")
            for name in names:
                path = Path(parent) / name
                if len(contents) >= _inspection_settings.MAX_FILES:
                    raise _inspection_errors.InspectionError("skill_revision_too_large")
                data = _read_regular(path, _inspection_settings.MAX_FILE_BYTES)
                total += len(data)
                if total > _inspection_settings.MAX_BUNDLE_BYTES:
                    raise _inspection_errors.InspectionError("skill_revision_too_large")
                contents[path.relative_to(bundle).as_posix()] = data
        if (
            "SKILL.md" not in contents
            or record.get("skill_id") != skill_id
            or record.get("revision_id") != revision_id
            or record.get("tree_hash") != revision_id
            or tree_hash(contents) != revision_id
            or file_hashes(contents) != record.get("file_hashes")
        ):
            raise _inspection_errors.InspectionError("skill_revision_unavailable")
        files = []
        for path, data in sorted(contents.items()):
            digest = record["file_hashes"][path]
            try:
                text = data.decode("utf-8") if b"\0" not in data else None
            except UnicodeDecodeError:
                text = None
            item = {
                "path": path,
                "bytes": len(data),
                "file_hash": digest,
                "kind": "text" if text is not None else "binary",
                "text": text,
            }
            # Inline only inert raster image formats from the same verified snapshot.
            mime = (
                "image/png"
                if data.startswith(b"\x89PNG\r\n\x1a\n")
                else (
                    "image/jpeg"
                    if data.startswith(b"\xff\xd8\xff")
                    else (
                        "image/gif"
                        if data.startswith((b"GIF87a", b"GIF89a"))
                        else (
                            "image/webp"
                            if data.startswith(b"RIFF") and data[8:12] == b"WEBP"
                            else None
                        )
                    )
                )
            )
            if include_images and mime:
                item["image_data_url"] = (
                    "data:" + mime + ";base64," + base64.b64encode(data).decode("ascii")
                )
            files.append(item)
        return {
            "schema_version": "laomedo.skill-inspection.v1",
            "skill_id": skill_id,
            "revision_id": revision_id,
            "tree_hash": revision_id,
            "files": files,
        }
    except _inspection_errors.InspectionError:
        raise
    except (OSError, _registry_errors.SkillStoreError, ValueError, KeyError, TypeError):
        raise _inspection_errors.InspectionError("skill_revision_unavailable") from None
