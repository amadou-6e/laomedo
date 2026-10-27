"""One-time migration of explicitly selected graphs, source and launchers.

No runtime import hooks are installed. Historical execution evidence is never
selected automatically. Writes are atomic per file, with exclusive backups.
"""
from __future__ import annotations

import argparse
import ast
import codecs
import json
import os
from pathlib import Path
import re
import stat
import tempfile

MODULE_PATHS = json.loads(Path(__file__).with_name("module-paths.json").read_text())
LAUNCH_FIELDS = {"module", "factory", "app_factory", "command", "args", "argv", "arguments", "entrypoint"}


class ManualMigrationRequired(ValueError):
    """Selected source contains a retired import that cannot be safely parsed."""


def migrate_source(source: str) -> str:
    """Rewrite retired imports while preserving aliases and statement structure."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        tree = None
        for match in re.finditer(r"from\s+(laomedo(?:\.\w+)*)\s+import\s*(\([^)]*\)|[^\n;]*)", source):
            if any(match[1] + "." + name in MODULE_PATHS for name in re.findall(r"\b\w+\b", match[2])):
                raise ManualMigrationRequired("Source cannot be parsed and contains retired imports; manual migration is required") from None
    if tree is not None:
        lines = source.splitlines(keepends=True)
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line))
        replacements = []
        newline = "\r\n" if "\r\n" in source else "\n"
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
                continue
            if not any(node.module + "." + item.name in MODULE_PATHS for item in node.names):
                continue
            statements = []
            for item in node.names:
                module = MODULE_PATHS.get(node.module + "." + item.name)
                if module is None:
                    statements.append("from " + node.module + " import " + item.name +
                                      (" as " + item.asname if item.asname else ""))
                    continue
                parent, name = module.rsplit(".", 1)
                alias = item.asname or item.name
                statements.append("from " + parent + " import " + name +
                                  (" as " + alias if alias != name else ""))
            start_column = len(lines[node.lineno - 1].encode()[:node.col_offset].decode())
            end_column = len(lines[node.end_lineno - 1].encode()[:node.end_col_offset].decode())
            separator = "; " if lines[node.lineno - 1][:start_column].strip() else newline + " " * start_column
            replacements.append((offsets[node.lineno - 1] + start_column,
                                 offsets[node.end_lineno - 1] + end_column,
                                 separator.join(statements)))
        for start, end, replacement in sorted(replacements, reverse=True):
            source = source[:start] + replacement + source[end:]
    for old, new in sorted(MODULE_PATHS.items(), key=lambda item: -len(item[0])):
        source = re.sub(r"(?<![\w.])" + re.escape(old) + r"(?!\w)", lambda match: new, source)
    return source


def _is_graph(value) -> bool:
    return isinstance(value, dict) and (isinstance(value.get("nodes"), list) or
           isinstance(value.get("data"), dict) and isinstance(value["data"].get("nodes"), list))


def _selected_field(path: tuple, graph: bool) -> bool:
    if "nodes" in path and path[-3:] == ("template", "code", "value"):
        return True
    if graph:
        return False
    if path in {("code",), ("code", "value")}:
        return True
    if path and path[0] == "launcher":
        path = path[1:]
    return bool(path and path[0] in LAUNCH_FIELDS and all(isinstance(p, int) for p in path[1:]))


def migrate_value(value):
    """Migrate graph code or explicit launcher fields, leaving other values alone."""
    graph = _is_graph(value)
    def walk(item, path):
        if isinstance(item, str):
            return migrate_source(item) if _selected_field(path, graph) else item
        if isinstance(item, list):
            return [walk(child, path + (index,)) for index, child in enumerate(item)]
        if isinstance(item, dict):
            return {key: walk(child, path + (key,)) for key, child in item.items()}
        return item
    return walk(value, ())


def migrate_json_source(source: str) -> str:
    """Splice changed JSON string tokens only; preserve all other source bytes."""
    graph = _is_graph(json.loads(source))
    decoder = json.JSONDecoder()
    replacements = []
    def whitespace(index):
        while index < len(source) and source[index] in " \t\r\n":
            index += 1
        return index
    def value(index, path):
        index = whitespace(index)
        if source[index] == "{":
            index = whitespace(index + 1)
            if source[index] == "}":
                return index + 1
            while True:
                key, end = decoder.raw_decode(source, index)
                index = value(whitespace(end) + 1, path + (key,))
                index = whitespace(index)
                if source[index] == "}":
                    return index + 1
                index = whitespace(index + 1)
        if source[index] == "[":
            index = whitespace(index + 1)
            if source[index] == "]":
                return index + 1
            count = 0
            while True:
                index = whitespace(value(index, path + (count,)))
                if source[index] == "]":
                    return index + 1
                index = whitespace(index + 1)
                count += 1
        item, end = decoder.raw_decode(source, index)
        if isinstance(item, str) and _selected_field(path, graph):
            migrated = migrate_source(item)
            if migrated != item:
                token = source[index:end]
                replacements.append((index, end, json.dumps(migrated, ensure_ascii=token.isascii())))
        return end
    value(0, ())
    for start, end, replacement in sorted(replacements, reverse=True):
        source = source[:start] + replacement + source[end:]
    return source


def _atomic_write(path: Path, updated: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".migration-", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(updated)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Write changes and exclusive sibling backups")
    mode.add_argument("--check", action="store_true", help="Exit 1 if any selected file requires migration")
    args = parser.parse_args()
    plans = []
    try:
        for path in args.files:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
                parser.error("Select regular source/config/graph files under 16 MiB")
            original = path.read_bytes()
            bom = codecs.BOM_UTF8 if original.startswith(codecs.BOM_UTF8) else b""
            source = original[len(bom):].decode("utf-8")
            text = migrate_json_source(source) if path.suffix.lower() == ".json" else migrate_source(source)
            updated = bom + text.encode("utf-8")
            backup = path.with_name(path.name + ".before-module-migration")
            if original != updated and args.apply and (backup.exists() or backup.is_symlink()):
                parser.error("A migration backup already exists for " + str(path))
            plans.append((path, original, updated, backup))
    except (ValueError, OSError, UnicodeError) as error:
        parser.error(str(error))
    # Preflight all inputs/backups before the first mutation. Atomicity is per file.
    for path, original, updated, backup in plans:
        if original == updated:
            print(str(path) + ": current")
            continue
        if args.apply:
            if path.read_bytes() != original:
                parser.error("File changed during migration: " + str(path))
            descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as output:
                output.write(original)
                output.flush()
                os.fsync(output.fileno())
            _atomic_write(path, updated)
        print(str(path) + (": migrated" if args.apply else ": migration required"))
    if args.check and any(original != updated for _, original, updated, _ in plans):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
