"""Explicit import-only copies for internal controls, never live probe acceptance."""

import ast
from hashlib import sha256
import importlib
import json
from pathlib import Path
import sys
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


def refuse_private_git_api(*_args, **_kwargs):
    """Refuse before an unsupported historical process API can perform an effect."""
    raise RuntimeError(
        "Historical experiment: private Git process helpers were removed. "
        "Manually migrate this entrypoint to laomedo.git and revalidate authorization."
    )


def load_retained_shared(name):
    """Load only an inventoried copy; preserve hashes and all non-import AST nodes."""
    inventory = json.loads(
        (ROOT / "tools/migrations/retained-shared-callers.json").read_text(
            encoding="utf-8"
        )
    )
    records = {item["module"]: item for item in inventory["files"]}
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
        for node in reversed(tree.body):
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
                ):
                    replacements.append(
                        "from retained_shared import refuse_private_git_api as " + alias
                    )
                    changed = True
                elif (
                    node.module == "laomedo.github.transport.rest.transport"
                    and item.name == "_NoRedirect"
                ):
                    replacements.append(
                        "from laomedo.http.redirect import NoRedirect as " + alias
                    )
                    changed = True
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
            ]
        if ast.dump(before) != ast.dump(after):
            raise ValueError("Historical Shared copy changes non-import code")
        parent_name, attribute = name.rsplit(".", 1)
        parent = importlib.import_module(parent_name)
        module = ModuleType(name)
        module.__file__ = str(source_path)
        module.__package__ = parent_name
        module._retained_shared_sha256 = record["sha256"]
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
