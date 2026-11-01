"""Compute canonical policy, file and length-prefixed tree identities."""

from __future__ import annotations

import hashlib
import json
from laomedo.skills.registry.paths import validate_relative_path


def hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical_json(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def tree_hash(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for relative, data in sorted(files.items()):
        encoded = validate_relative_path(relative).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return "sha256:" + digest.hexdigest()


def file_hashes(files: dict[str, bytes]) -> dict[str, str]:
    return {path: hash_bytes(data) for path, data in sorted(files.items())}
