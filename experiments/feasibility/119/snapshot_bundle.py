"""Build a read-only sample skill snapshot from an explicit item manifest."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def safe_file(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or any(part in (".", "..") for part in path.parts):
        raise ValueError(f"unsafe relative path: {relative}")
    candidate = root.joinpath(*path.parts)
    has_link = any(root.joinpath(*path.parts[:index]).is_symlink() for index in range(1, len(path.parts) + 1))
    if has_link or not candidate.is_file() or not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"missing, linked, or escaped file: {relative}")
    return candidate


def section_bytes(content: bytes, heading: str) -> bytes:
    lines = content.splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if line.rstrip(b"\r\n").decode("utf-8") == heading]
    if len(matches) != 1:
        raise ValueError(f"heading must occur exactly once: {heading}")
    start = matches[0]
    level = len(heading) - len(heading.lstrip("#"))
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith(b"#"):
            next_level = len(line) - len(line.lstrip(b"#"))
            if next_level <= level and line[next_level : next_level + 1] == b" ":
                end = index
                break
    return b"".join(lines[start:end])


def build(root: Path, manifest: dict, selection: list[str]) -> dict:
    files = manifest["files"]
    if len(files) != len(set(files)) or "SKILL.md" not in files:
        raise ValueError("files must be unique and include SKILL.md")
    file_hashes = {relative: sha256(safe_file(root, relative).read_bytes()) for relative in files}
    item_ids = [item["id"] for item in manifest["items"]]
    if len(item_ids) != len(set(item_ids)):
        raise ValueError("duplicate item ID")
    if not set(selection).issubset(item_ids):
        raise ValueError("unknown selected item ID")

    selected_files = {"SKILL.md"}
    item_records = []
    for item in manifest["items"]:
        source = item["source"]
        requirements = item.get("requires", [])
        for relative in [source["path"], *requirements]:
            if relative not in file_hashes:
                raise ValueError(f"undeclared dependency: {relative}")
        content = safe_file(root, source["path"]).read_bytes()
        content_hash = sha256(section_bytes(content, source["heading"]))
        item_records.append({"id": item["id"], "kind": item["kind"], "source": source, "content_hash": content_hash})
        if item["id"] in selection:
            selected_files.update([source["path"], *requirements])

    canonical_tree = "".join(f"{path}\0{file_hashes[path]}\n" for path in sorted(file_hashes))
    tree_hash = sha256(canonical_tree.encode("utf-8"))
    return {
        "schema_version": 1,
        "skill_id": manifest["skill_id"],
        "revision_id": tree_hash,
        "tree_hash": tree_hash,
        "file_hashes": dict(sorted(file_hashes.items())),
        "items": item_records,
        "selection": {
            "item_ids": selection,
            "dependency_files": sorted(selected_files),
            "delivery_mode": "direct_context_required",
            "reason": "Native loading of SKILL.md exposes all its sections, not only the selected item.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--select", action="append", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = json.dumps(build(args.source.resolve(strict=True), manifest, args.select), indent=2) + "\n"
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
