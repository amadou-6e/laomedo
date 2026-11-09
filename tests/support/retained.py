"""Explicit dependency-loading copies for internal controls, never live acceptance."""

from support.paths import repository_root

import ast
from hashlib import sha256
import importlib
import json
from pathlib import Path
import sys
from types import ModuleType

ROOT = repository_root()


def refuse_private_git_api(*_args, **_kwargs):
    """Refuse before an unsupported historical process API can perform an effect."""
    raise RuntimeError(
        "Historical experiment: private Git process helpers were removed. "
        "Manually migrate this entrypoint to laomedo.git and revalidate authorization."
    )


def load_retained_shared(name):
    """Preserve hashes and code outside exact inventoried import/loader statements.

    Only pinned top-level from-imports and declared dependency loader bindings
    are supported; arbitrary aliases, dynamic APIs and live entrypoints are not.
    """
    inventory = json.loads(
        (ROOT / "tools/migrations/retained-shared-callers.json").read_text(
            encoding="utf-8"
        )
    )
    records = {item["module"]: item for item in inventory["files"]}
    module_paths = json.loads(
        (ROOT / "tools/migrations/module-paths.json").read_text(encoding="utf-8")
    )
    symbol_paths = json.loads(
        (ROOT / "tools/migrations/symbol-paths.json").read_text(encoding="utf-8")
    )
    if name not in records:
        raise ValueError("Historical Shared caller is not inventoried")
    record = records[name]
    source_path = ROOT / record["path"]
    raw = source_path.read_bytes()
    if sha256(raw).hexdigest() != record["sha256"]:
        raise ValueError("Historical Shared caller bytes differ from inventory")
    if name in sys.modules:
        module = sys.modules[name]
        if getattr(module, "_retained_shared_sha256", None) != record["sha256"]:
            raise ValueError("Historical Shared caller was loaded without adaptation")
        return module
    previous_path = sys.path[:]
    try:
        sys.path.insert(0, str(ROOT))
        for dependency in record["dependencies"]:
            load_retained_shared(dependency)
        source = raw.decode("utf-8-sig")
        lines = source.splitlines(keepends=True)
        tree = ast.parse(source)
        dependency_bindings = record.get("dependency_bindings", {})
        for node in reversed(tree.body):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in dependency_bindings
            ):
                binding = node.targets[0].id
                if not (
                    isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute)
                    and node.value.func.attr == "module_from_spec"
                ):
                    raise ValueError("Inventoried dependency assignment shape changed")
                replacement = (
                    binding
                    + " = load_retained_shared("
                    + repr(dependency_bindings[binding])
                    + ")\n"
                )
                lines[node.lineno - 1 : node.end_lineno] = [replacement] + ["\n"] * (
                    node.end_lineno - node.lineno
                )
            elif (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "exec_module"
                and len(node.value.args) == 1
                and isinstance(node.value.args[0], ast.Name)
                and node.value.args[0].id in dependency_bindings
            ):
                lines[node.lineno - 1 : node.end_lineno] = ["\n"] * (
                    node.end_lineno - node.lineno + 1
                )
        for node in reversed(tree.body):
            if isinstance(node, ast.Import):
                statements = []
                changed = False
                for item in node.names:
                    target = (
                        module_paths.get(item.name, item.name)
                        if item.name.startswith(("laomedo.skills.", "laomedo.github."))
                        else item.name
                    )
                    statements.append(
                        "import "
                        + target
                        + (" as " + item.asname if item.asname else "")
                    )
                    changed |= target != item.name
                if changed:
                    lines[node.lineno - 1 : node.end_lineno] = [
                        "\n".join(statements) + "\n"
                    ]
                continue
            if not isinstance(node, ast.ImportFrom):
                continue
            replacements = []
            changed = False
            for item in node.names:
                alias = item.asname or item.name
                if (
                    node.module == "laomedo.github.transport.git.utils"
                    and item.name
                    in {
                        "_base_git_environment",
                        "_credential_environment",
                        "_run_bounded_tree",
                    }
                ) or (
                    node.module == "laomedo.agents.workspaces"
                    and item.name in {"_git_environment", "_bounded_git"}
                ):
                    replacements.append(
                        "from support.retained import refuse_private_git_api as "
                        + alias
                    )
                    changed = True
                elif (
                    node.module
                    in {
                        "laomedo.github.transport.rest.transport",
                        "laomedo.github.transport.rest",
                    }
                    and item.name == "_NoRedirect"
                ):
                    replacements.append(
                        "from laomedo.http.redirect import NoRedirect as " + alias
                    )
                    changed = True
                elif node.module.startswith(
                    (
                        "laomedo.skills.",
                        "laomedo.github.",
                        "laomedo.agents.",
                        "laomedo.activity.",
                    )
                ):
                    full = node.module + "." + item.name
                    target = symbol_paths.get(
                        full,
                        module_paths.get(node.module, node.module) + "." + item.name,
                    )
                    module, symbol = target.rsplit(".", 1)
                    replacements.append(
                        "from "
                        + module
                        + " import "
                        + symbol
                        + (" as " + alias if alias != symbol else "")
                    )
                    changed |= target != full
                else:
                    replacements.append(
                        "from "
                        + node.module
                        + " import "
                        + item.name
                        + (" as " + item.asname if item.asname else "")
                    )
            if changed:
                lines[node.lineno - 1 : node.end_lineno] = [
                    "\n".join(replacements) + "\n"
                ]
        migrated = "".join(lines)
        before, after = ast.parse(source), ast.parse(migrated)
        for parsed in (before, after):
            parsed.body = [
                node
                for node in parsed.body
                if not isinstance(node, (ast.Import, ast.ImportFrom))
                and not (
                    isinstance(node, ast.Assign)
                    and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id in dependency_bindings
                )
                and not (
                    isinstance(node, ast.Expr)
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute)
                    and node.value.func.attr == "exec_module"
                    and len(node.value.args) == 1
                    and isinstance(node.value.args[0], ast.Name)
                    and node.value.args[0].id in dependency_bindings
                )
            ]
        if ast.dump(before) != ast.dump(after):
            raise ValueError("Historical Shared copy changes non-import code")
        parent_name, attribute = name.rsplit(".", 1)
        parent = importlib.import_module(parent_name)
        module = ModuleType(name)
        module.__file__ = str(source_path)
        module.__package__ = parent_name
        module._retained_shared_sha256 = record["sha256"]
        if dependency_bindings:
            module.load_retained_shared = load_retained_shared
        sys.modules[name] = module
        try:
            exec(compile(migrated, str(source_path), "exec"), module.__dict__)
        except BaseException:
            sys.modules.pop(name, None)
            raise
        setattr(parent, attribute, module)
        return module
    finally:
        sys.path[:] = previous_path
