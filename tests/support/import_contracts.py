"""Inspect maintained Python and embedded graph code without executing it."""

import ast
import json


def maintained_sources(root):
    protected = set()
    for manifest in (root / "tools/migrations").glob("retained-*-callers.json"):
        protected.update(
            row["path"]
            for row in json.loads(manifest.read_text(encoding="utf-8"))["files"]
        )
    for directory in ("src", "components", "tests", "examples"):
        for path in (root / directory).rglob("*.py"):
            if path.relative_to(root).as_posix() not in protected:
                yield path.relative_to(root).as_posix(), path.read_text(
                    encoding="utf-8-sig"
                )
    # Maintained node identities are owned by the canonical-source contract.
    # Other saved exports are historical evidence, not executable current templates.
    manifest = json.loads(
        (root / "tests/contracts/component-templates.json").read_text(encoding="utf-8")
    )
    assert manifest["files"], "Maintained graph inventory must not be empty"
    for record in manifest["files"]:
        path = root / record["path"]
        graph = json.loads(path.read_text(encoding="utf-8-sig"))
        nodes = {
            node["id"]: node
            for node in graph.get("nodes", graph.get("data", {}).get("nodes", []))
        }
        for item in record["nodes"]:
            yield from embedded_sources(
                nodes[item["node_id"]], record["path"] + ":" + item["node_id"]
            )


def embedded_sources(value, label):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "code":
                code = item.get("value") if isinstance(item, dict) else item
                if isinstance(code, str):
                    yield label + ":code", code
            else:
                yield from embedded_sources(item, label)
    elif isinstance(value, list):
        for item in value:
            yield from embedded_sources(item, label)


def retired_imports(root, module_paths, symbol_paths):
    retired = {
        name
        for name, target in module_paths.items()
        if name != target
        and not root.joinpath("src", *name.split(".")).with_suffix(".py").exists()
        and not root.joinpath("src", *name.split("."), "__init__.py").exists()
    }
    violations = []
    count = 0
    for label, source in maintained_sources(root):
        count += 1
        for node in ast.walk(ast.parse(source, filename=label)):
            if isinstance(node, ast.Import):
                names = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
                for item in node.names:
                    old = (node.module or "") + "." + item.name
                    target = symbol_paths.get(old, old)
                    if target != old:
                        violations.append((label, node.lineno, old, target))
            else:
                continue
            for name in names:
                if name in retired:
                    violations.append((label, node.lineno, name, module_paths[name]))
    assert count, "Maintained import scan must not be empty"
    return violations
