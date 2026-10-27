"""Migrate explicitly selected saved graphs and launchers to canonical imports.

This is a one-time source migration, not a runtime import compatibility layer.
Historical execution evidence is never selected or rewritten automatically.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re

MODULE_PATHS = json.loads(Path(__file__).with_name("module-paths.json").read_text())


def migrate_source(source: str) -> str:
    """Return source with retired module references rewritten to their owners."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        tree = None
    if tree is not None:
        lines = source.splitlines(keepends=True)
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line))
        replacements = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module != "laomedo":
                continue
            if not any("laomedo." + item.name in MODULE_PATHS for item in node.names):
                continue
            statements = []
            for item in node.names:
                module = MODULE_PATHS.get("laomedo." + item.name)
                if module is None:
                    statements.append("from laomedo import " + item.name +
                                      (" as " + item.asname if item.asname else ""))
                    continue
                parent, name = module.rsplit(".", 1)
                alias = item.asname or item.name
                statements.append("from " + parent + " import " + name +
                                  (" as " + alias if alias != name else ""))
            start_column = len(lines[node.lineno - 1].encode()[:node.col_offset].decode())
            end_column = len(lines[node.end_lineno - 1].encode()[:node.end_col_offset].decode())
            separator = "; " if lines[node.lineno - 1][:start_column].strip() else "\n" + " " * start_column
            replacements.append((offsets[node.lineno - 1] + start_column,
                                 offsets[node.end_lineno - 1] + end_column,
                                 separator.join(statements)))
        for start, end, replacement in sorted(replacements, reverse=True):
            source = source[:start] + replacement + source[end:]
    for old, new in sorted(MODULE_PATHS.items(), key=lambda item: -len(item[0])):
        source = re.sub(r"(?<![\w.])" + re.escape(old) + r"(?!\w)", lambda match: new, source)
    return source


def migrate_value(value, field=None):
    """Rewrite code and launcher fields, preserving graph identities and content."""
    if isinstance(value, str):
        return migrate_source(value) if field in {"code", "module", "factory", "app_factory", "command", "args", "argv", "arguments", "entrypoint"} else value
    if isinstance(value, list):
        return [migrate_value(item, field) for item in value]
    if isinstance(value, dict):
        return {key: migrate_value(item, "code" if field == "code" and key == "value" else key)
                for key, item in value.items()}
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--apply", action="store_true", help="Write changes and a sibling backup")
    args = parser.parse_args()
    for path in args.files:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
            parser.error("Select regular source/config/graph files under 16 MiB")
        source = path.read_text(encoding="utf-8-sig")
        if path.suffix.lower() == ".json":
            value = json.loads(source)
            migrated = migrate_value(value)
            updated = json.dumps(migrated, indent=2) + "\n" if migrated != value else source
        else:
            updated = migrate_source(source)
        if updated == source:
            print(str(path) + ": current")
            continue
        if args.apply:
            backup = path.with_name(path.name + ".before-module-migration")
            # Exclusive creation preserves an earlier backup rather than overwriting it.
            with backup.open("xb") as output:
                output.write(path.read_bytes())
            path.write_text(updated, encoding="utf-8")
        print(str(path) + (": migrated" if args.apply else ": migration required"))


if __name__ == "__main__":
    main()
