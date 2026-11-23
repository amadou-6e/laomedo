"""Publish a staged preview without removing files used by existing tabs."""

import hashlib
import os
from pathlib import Path
from shutil import copyfile
from uuid import uuid4


def publish():
    root = Path("C:/CodeWorkspace/laomedo/.tools").resolve()
    staged = (root / "assistant-stability-row-build").resolve()
    target = (root / "assistant-282-upstream/src/frontend/build").resolve()
    if not staged.is_relative_to(root) or not target.is_relative_to(root):
        raise RuntimeError("preview_target_outside_workspace")
    if not (staged / "index.html").is_file() or not (target / "index.html").is_file():
        raise RuntimeError("complete_staged_and_live_build_required")
    files = sorted(path for path in staged.rglob("*") if path.is_file())
    # New asset hashes land first. Retained old hashes keep lazy-loaded code in
    # existing tabs available. Only the final HTML entry switches versions.
    files = [path for path in files if path.name != "index.html"] + [
        staged / "index.html"
    ]
    copied = 0
    for source in files:
        destination = target / source.relative_to(staged)
        if source.is_symlink() or not destination.resolve().is_relative_to(target):
            raise RuntimeError("preview_file_outside_target")
        content = source.read_bytes()
        if (
            destination.is_file()
            and hashlib.sha256(destination.read_bytes()).digest()
            == hashlib.sha256(content).digest()
        ):
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + "." + uuid4().hex + ".tmp")
        copyfile(source, temporary)
        os.replace(temporary, destination)
        copied += 1
    print(
        f"Published staged entry after {copied} atomic file replacements; retained previous assets."
    )


if __name__ == "__main__":
    publish()
