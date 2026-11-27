"""Inspect public error producers without executing provider paths."""

import ast
import json
import re
from pathlib import Path
from support.paths import repository_root
from test_shared.test_errors.settings import ERROR_FIELDS

ROOT = repository_root()


def producer_paths(filename):
    """Resolve a historical producer label to existing defining source files.

    Return checkout paths; fail if any declared owner is absent. No code executes.
    """
    if "/" in filename:
        path = ROOT / "src/laomedo" / filename
        if not path.is_file():
            raise AssertionError("Missing defining error producer: " + filename)
        return [path]
    module = "laomedo." + Path(filename).stem
    mapping = json.loads((ROOT / "tools/migrations/module-paths.json").read_text())
    symbols = json.loads((ROOT / "tools/migrations/symbol-paths.json").read_text())
    prefix = mapping[module].rsplit(".", 1)[0] + "."
    owners = {mapping[module]} | {
        value.rsplit(".", 1)[0]
        for key, value in symbols.items()
        if key.startswith(module + ".")
        and value.startswith(prefix)
        and not value in mapping.values()
    }
    owners.update(
        ".".join(path.relative_to(ROOT / "src").with_suffix("").parts)
        for path in ROOT.joinpath("src", *mapping[module].split(".")[:-1]).glob("*.py")
        if path.name != "__init__.py"
    )
    if filename == "local_runner.py":
        owners.update(
            {"laomedo.agents.agents.base.agent", "laomedo.agents.agents.base.utils"}
        )
    paths = sorted(
        ROOT.joinpath("src", *owner.split(".")).with_suffix(".py") for owner in owners
    )
    if not paths or any(not path.is_file() for path in paths):
        raise AssertionError("Missing defining error producer: " + module)
    return paths


def producer_path(filename):
    """Return the mapped primary source path for a historical producer label."""
    module = json.loads((ROOT / "tools/migrations/module-paths.json").read_text())[
        "laomedo." + Path(filename).stem
    ]
    return ROOT.joinpath("src", *module.split(".")).with_suffix(".py")


def emitted_codes(source):
    """Inspect public literals, not every underscore-containing data-field name.

    Dynamic external failures use the presenter's safe fallback; they are not
    assumed covered by this literal guard.
    """
    tree = ast.parse(source)
    candidates = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and node.exc.args
        ):
            candidates.append(node.exc.args[0])
        if isinstance(node, ast.Call):
            candidates.extend(
                keyword.value
                for keyword in node.keywords
                if keyword.arg in ERROR_FIELDS
            )
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "setdefault"
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value in ERROR_FIELDS
            ):
                candidates.append(node.args[1])
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr in ERROR_FIELDS:
                    candidates.append(node.value)
                elif (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.slice, ast.Constant)
                    and target.slice.value in ERROR_FIELDS
                ):
                    candidates.append(node.value)
        if isinstance(node, ast.Dict):
            candidates.extend(
                value
                for key, value in zip(node.keys, node.values)
                if isinstance(key, ast.Constant) and key.value in ERROR_FIELDS
            )

    def literals(node):
        if isinstance(node, ast.Constant):
            yield node.value
        elif isinstance(node, ast.IfExp):
            yield from literals(node.body)
            yield from literals(node.orelse)
        elif isinstance(node, ast.BoolOp):
            for value in node.values:
                yield from literals(value)

    return {
        value
        for candidate in candidates
        for value in literals(candidate)
        if isinstance(value, str)
        and re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+", value)
    }
