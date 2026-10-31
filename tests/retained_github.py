"""Explicit import-only adaptation of byte-pinned probes for internal controls.

This helper installs no import hook and never invokes a probe's main function.
The named archived probe modules remain original files; live use requires an explicit
migrated copy. These internal imports are not live integration evidence.
"""

import ast
from hashlib import sha256
import importlib
import json
from pathlib import Path
import runpy
import sys
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


def load_retained_github(name, *, manifest="retained-github-callers.json"):
    """Load one manifest-allowlisted probe after a hash-checked import-only rewrite.

    Only the named retained dependency edges are loaded recursively. Exact
    module names are registered so existing fixture monkeypatches stay attached
    to that selected copy. No finder, facade or broad migration is installed.
    """
    if manifest not in {"retained-github-callers.json", "retained-http-callers.json"}:
        raise ValueError("Retained probe inventory not admitted")
    manifest = json.loads(Path(ROOT, "tools/migrations", manifest).read_text())
    records = {
        item["path"].removesuffix(".py").replace("/", "."): item
        for item in manifest["files"]
    }
    if name not in records:
        raise ValueError("Probe is not an explicitly retained GitHub caller")
    record = records[name]
    path = Path(ROOT, record["path"])
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != record["sha256"]:
        raise ValueError("Retained GitHub caller source hash mismatch")
    existing = sys.modules.get(name)
    if existing is not None:
        if getattr(existing, "_retained_github_sha256", None) != record["sha256"]:
            raise ValueError("Retained GitHub caller was loaded without adaptation")
        return existing
    dependency = {
        "experiments.exp100.probe_native_capture": "experiments.exp104.probe_active_delivery",
        "experiments.exp100.probe_paired": "experiments.exp104.probe_active_delivery",
        "experiments.exp139.runtime": "experiments.exp139.prepare",
    }.get(name)
    if dependency is not None:
        load_retained_github(dependency)
    previous_path = sys.path[:]
    try:
        sys.path[:0] = [str(ROOT), str(Path(ROOT, "tools/migrations"))]
        migration = runpy.run_path(
            str(Path(ROOT, "tools/migrations/migrate_module_paths.py"))
        )
        source = raw.decode("utf-8")
        # Full-source migration deliberately still rejects old run= constructor
        # contracts. These fixtures adapt imports only; their historical native
        # entrypoints remain unsupported and must never be dispatched here.
        lines = source.splitlines(keepends=True)
        imports = [
            node
            for node in ast.parse(source).body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        for node in reversed(imports):
            original = "".join(lines[node.lineno - 1 : node.end_lineno])
            lines[node.lineno - 1 : node.end_lineno] = [
                migration["migrate_source"](original)
            ]
        migrated = "".join(lines)
        trees = [ast.parse(value) for value in (source, migrated)]
        for tree in trees:
            tree.body = [
                node
                for node in tree.body
                if not isinstance(node, (ast.Import, ast.ImportFrom))
            ]
        if ast.dump(trees[0]) != ast.dump(trees[1]):
            raise ValueError("Retained GitHub caller migration changed non-import code")
        parent_name, attribute = name.rsplit(".", 1)
        parent = importlib.import_module(parent_name)
        module = ModuleType(name)
        module.__file__ = str(path)
        module.__package__ = parent_name
        module._retained_github_sha256 = record["sha256"]
        sys.modules[name] = module
        try:
            exec(compile(migrated, str(path), "exec"), module.__dict__)
        except BaseException:
            sys.modules.pop(name, None)
            raise
        setattr(parent, attribute, module)
        return module
    finally:
        sys.path[:] = previous_path
