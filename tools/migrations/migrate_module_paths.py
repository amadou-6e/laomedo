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
from migration_errors import ManualMigrationRequired

MODULE_PATHS = json.loads(Path(__file__).with_name("module-paths.json").read_text())

SYMBOL_PATHS = json.loads(Path(__file__).with_name("symbol-paths.json").read_text())
CLI_PATHS = json.loads(Path(__file__).with_name("cli-paths.json").read_text())
if set(MODULE_PATHS.values()) & set(MODULE_PATHS):
    raise ValueError("Migration map targets must be final modules")
SYMBOL_PATTERN = re.compile(
    r"(?<![\w.])(?:"
    + "|".join(re.escape(k) for k in sorted(SYMBOL_PATHS, key=len, reverse=True))
    + r")(?!\w)"
)
MODULE_PATTERN = re.compile(
    r"(?<![\w.])(?:"
    + "|".join(re.escape(k) for k in sorted(MODULE_PATHS, key=len, reverse=True))
    + r")(?![\w.])"
)

LAUNCH_FIELDS = {
    "module",
    "factory",
    "app_factory",
    "command",
    "args",
    "argv",
    "arguments",
    "entrypoint",
}


def _physical_lines(source: str) -> list[str]:
    """Python physical lines exclude form feeds and Unicode text separators."""
    return [line for line in re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)", source) if line]


def migrate_source(source: str) -> str:
    """Rewrite published imports to defining modules; refuse ambiguous symbols."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        tree = None
        if re.search(r"\b(?:from|import)\s+laomedo", source):
            raise ManualMigrationRequired(
                "Source cannot be parsed; manual migration of its Laomedo imports is required"
            ) from None
    replacements, aliases, additional = [], {}, set()
    changed_parameters = set()
    capture_returns = set()
    activity_store_imported = False
    changed_models = set()
    if tree is not None:
        # AST columns count UTF-8 bytes, using Python's physical line boundaries.
        lines = _physical_lines(source)
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line))

        def position(line, column):
            return offsets[line - 1] + len(lines[line - 1].encode()[:column].decode())

        def replace(node, value):
            replacements.append(
                (
                    position(node.lineno, node.col_offset),
                    position(node.end_lineno, node.end_col_offset),
                    value,
                )
            )

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and not node.level:
                statements, changed = [], False
                for item in node.names:
                    full = node.module + "." + item.name
                    if full == "laomedo.activity.agent_activity.store.ActivityStore":
                        activity_store_imported = True
                    if full in MODULE_PATHS:
                        target = MODULE_PATHS[full]
                        alias = item.asname or item.name
                        parent, name = target.rsplit(".", 1)
                        statements.append(
                            "from "
                            + parent
                            + " import "
                            + name
                            + (" as " + alias if alias != name else "")
                        )
                        aliases[alias] = full
                        changed = True
                    elif full in SYMBOL_PATHS:
                        target, name = SYMBOL_PATHS[full].rsplit(".", 1)
                        if name == "LeaseHTTPServer":
                            raise ManualMigrationRequired("Lease handler construction now belongs to LeaseHTTPServer; manual migration is required")
                        if name in {
                            "WorkItem",
                            "Dependency",
                            "GraphSnapshot",
                            "VerifiedStage",
                        }:
                            changed_models.add(item.asname or item.name)
                        if name == "ActivityStore":
                            activity_store_imported = True
                        if name == "capture_for":
                            capture_returns.add(item.asname or item.name)
                        if name in {
                            "inspect_exact",
                            "cleanup_exact",
                            "cleanup_after_loss",
                        }:
                            changed_parameters.add(item.asname or item.name)
                        statements.append(
                            "from "
                            + target
                            + " import "
                            + name
                            + (
                                " as " + (item.asname or item.name)
                                if (item.asname or item.name) != name
                                else ""
                            )
                        )
                        changed = True
                    elif node.module in MODULE_PATHS:
                        raise ManualMigrationRequired(
                            "No safe symbol mapping for "
                            + full
                            + "; manual migration is required"
                        )
                    else:
                        statements.append(
                            "from "
                            + node.module
                            + " import "
                            + item.name
                            + (" as " + item.asname if item.asname else "")
                        )
                if changed:
                    replace(node, "; ".join(statements))
            elif isinstance(node, ast.Import):
                statements, changed = [], False
                for item in node.names:
                    target = MODULE_PATHS.get(item.name, item.name)
                    statements.append(
                        "import "
                        + target
                        + (" as " + item.asname if item.asname else "")
                    )
                    if item.asname:
                        aliases[item.asname] = item.name
                    changed |= target != item.name
                if changed:
                    replace(node, "; ".join(statements))
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "run_module"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value in CLI_PATHS
            ):
                replace(node.args[0], repr(CLI_PATHS[node.args[0].value]))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id in capture_returns
                and any(
                    isinstance(target, (ast.Tuple, ast.List)) for target in node.targets
                )
            ):
                raise ManualMigrationRequired(
                    "capture_for now returns ActivityInvocation; manual migration must use .store and .invocation_id"
                )
            if isinstance(node, ast.Call):
                if changed_models and (
                    isinstance(node.func, ast.Name)
                    and node.func.id in {"asdict", "replace"}
                    or isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "dataclasses"
                    and node.func.attr in {"asdict", "replace"}
                ):
                    raise ManualMigrationRequired(
                        "Domain records are now Pydantic models; manual migration must use model_dump or model_validate"
                    )
                if (
                    isinstance(node.func, ast.Name)
                    and node.func.id in changed_models
                    and node.args
                ):
                    raise ManualMigrationRequired(
                        "Pydantic model construction requires named fields; manual migration of positional arguments is required"
                    )
                if (
                    isinstance(node.func, ast.Name)
                    and node.func.id in {"getattr", "setattr", "hasattr"}
                    and node.args
                    and isinstance(node.args[0], ast.Name)
                    and aliases.get(node.args[0].id) in MODULE_PATHS
                ):
                    raise ManualMigrationRequired(
                        "Dynamic access to a retired module requires manual migration to the defining symbol"
                    )
                name = node.func.id if isinstance(node.func, ast.Name) else ""
                full = ast.unparse(node.func)
                if (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in aliases
                ):
                    full = aliases[node.func.value.id] + "." + node.func.attr
                target = SYMBOL_PATHS.get(full, "")
                if (
                    activity_store_imported
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "start"
                    and len(node.args) >= 3
                ):
                    raise ManualMigrationRequired(
                        "ActivityStore.start now takes CaptureIdentity; manual migration of this call is required"
                    )
                if len(node.args) >= 3 and (
                    name in changed_parameters
                    or target.rsplit(".", 1)[-1]
                    in {"inspect_exact", "cleanup_exact", "cleanup_after_loss"}
                ):
                    raise ManualMigrationRequired(
                        "Container cleanup now takes ContainerIdentity; manual migration of this call is required"
                    )
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in aliases
            ):
                original = aliases[node.value.id]
                full = original + "." + node.attr
                if full in SYMBOL_PATHS:
                    target, name = SYMBOL_PATHS[full].rsplit(".", 1)
                    if name == "LeaseHTTPServer":
                        raise ManualMigrationRequired("Lease handler construction now belongs to LeaseHTTPServer; manual migration is required")
                    if target != MODULE_PATHS.get(original, original) or name != node.attr:
                        alias = "_migrated_" + node.value.id + "_" + node.attr
                        additional.add(
                            "from " + target + " import " + name + " as " + alias
                        )
                        replace(node, alias)
                elif original in MODULE_PATHS:
                    raise ManualMigrationRequired(
                        "No safe attribute mapping for "
                        + full
                        + "; manual migration is required"
                    )
        for start, end, value in sorted(replacements, reverse=True):
            source = source[:start] + value + source[end:]
        if additional:
            parsed = ast.parse(source)
            line = 0
            for node in parsed.body:
                if (
                    isinstance(node, ast.Expr)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                    or isinstance(node, ast.ImportFrom)
                    and node.module == "__future__"
                ):
                    line = node.end_lineno
                else:
                    break
            parts = _physical_lines(source)
            newline = "\r\n" if "\r\n" in source else "\r" if "\r" in source else "\n"
            parts[line:line] = [newline.join(sorted(additional)) + newline]
            source = "".join(parts)
    source = SYMBOL_PATTERN.sub(lambda match: SYMBOL_PATHS[match.group()], source)
    # CLI arguments have different ownership from imported runtime objects.
    for old, new in CLI_PATHS.items():
        source = re.sub(
            r"(-m\s+)" + re.escape(old) + r"(?![\w.])", lambda m: m[1] + new, source
        )
        source = re.sub(
            r"(['\"]-m['\"]\s*,\s*['\"])" + re.escape(old) + r"(?=['\"])",
            lambda m: m[1] + new,
            source,
        )
    return MODULE_PATTERN.sub(lambda match: MODULE_PATHS[match.group()], source)


def _migrate_selected(value, path):
    if path and not ("nodes" in path or path[0] == "code") and value in CLI_PATHS:
        return CLI_PATHS[value]
    return migrate_source(value)


def _is_graph(value) -> bool:
    return isinstance(value, dict) and (
        isinstance(value.get("nodes"), list)
        or isinstance(value.get("data"), dict)
        and isinstance(value["data"].get("nodes"), list)
    )


def _selected_field(path: tuple, graph: bool) -> bool:
    if "nodes" in path and path[-3:] == ("template", "code", "value"):
        return True
    if graph:
        return False
    if path in {("code",), ("code", "value")}:
        return True
    if path and path[0] == "launcher":
        path = path[1:]
    return bool(
        path and path[0] in LAUNCH_FIELDS and all(isinstance(p, int) for p in path[1:])
    )


def migrate_value(value):
    """Migrate graph code or explicit launcher fields, leaving other values alone."""
    graph = _is_graph(value)

    def walk(item, path):
        if isinstance(item, str):
            return (
                _migrate_selected(item, path) if _selected_field(path, graph) else item
            )
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
            migrated = _migrate_selected(item, path)
            if migrated != item:
                token = source[index:end]
                replacements.append(
                    (index, end, json.dumps(migrated, ensure_ascii=token.isascii()))
                )
        return end

    value(0, ())
    for start, end, replacement in sorted(replacements, reverse=True):
        source = source[:start] + replacement + source[end:]
    return source


def _atomic_write(path: Path, updated: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(
        prefix="." + path.name + ".migration-", dir=path.parent
    )
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
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Write changes and exclusive sibling backups",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if any selected file requires migration",
    )
    args = parser.parse_args()
    plans = []
    try:
        for path in args.files:
            if (
                path.is_symlink()
                or not path.is_file()
                or path.stat().st_size > 16 * 1024 * 1024
            ):
                parser.error("Select regular source/config/graph files under 16 MiB")
            original = path.read_bytes()
            bom = codecs.BOM_UTF8 if original.startswith(codecs.BOM_UTF8) else b""
            source = original[len(bom) :].decode("utf-8")
            text = (
                migrate_json_source(source)
                if path.suffix.lower() == ".json"
                else migrate_source(source)
            )
            updated = bom + text.encode("utf-8")
            backup = path.with_name(path.name + ".before-module-migration")
            if (
                original != updated
                and args.apply
                and (backup.exists() or backup.is_symlink())
            ):
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
