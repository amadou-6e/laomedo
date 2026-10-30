"""Reproduce C3 interface control-flow contracts from exact baseline Git source.

Run from this checkout with --baseline REV --output PATH. No service is started.
Only imports, module docstrings and module-alias qualification are normalized;
the canonical named AST retains every other field and meaningful literal.
"""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess

from capture_http_handler_contracts import canonical_ast

BASELINE = "23cb11505c46ab24715055ad2abc09f3b1565d4f"


def module_pairs():
    for group in (
        "github.issues",
        "github.pull_requests",
        "skills.sources",
        "skills.operations",
    ):
        owner, feature = group.split(".")
        for leaf in ("client", "handler", "server", "cli", "settings"):
            yield f"laomedo.{group}.{leaf}", f"laomedo.{owner}.interface.{feature}.{leaf}"


def normalize_body(node, aliases):
    """Drop imports only; collapse actual Laomedo module-alias member reads."""
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in aliases
    ):
        return ast.Name(id=node.attr, ctx=node.ctx)
    for name, value in ast.iter_fields(node):
        if isinstance(value, list):
            setattr(
                node,
                name,
                [
                    normalize_body(item, aliases) if isinstance(item, ast.AST) else item
                    for item in value
                    if not isinstance(item, (ast.Import, ast.ImportFrom))
                ],
            )
        elif isinstance(value, ast.AST):
            setattr(node, name, normalize_body(value, aliases))
    return node


def normalized(source, *, selection="module"):
    tree = ast.parse(source)
    aliases = {
        alias.asname
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.asname and alias.name.startswith("laomedo.")
    }
    if selection == "Settings":
        tree = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "Settings"
        )
    elif selection == "fixed_source_policy":
        tree.body = [node for node in tree.body if isinstance(node, ast.Assign)]
    elif ast.get_docstring(tree):
        tree.body.pop(0)
    return canonical_ast(normalize_body(tree, aliases))


def encode_extra(value):
    if isinstance(value, bytes):
        return {"python_bytes_hex": value.hex()}
    if value is Ellipsis:
        return {"python_ellipsis": True}
    raise TypeError(type(value).__name__)


def source_digest(source, *, selection="module"):
    data = json.dumps(
        normalized(source, selection=selection),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=encode_extra,
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def baseline_source(root, revision, module):
    relative = "src/" + module.replace(".", "/") + ".py"
    return subprocess.check_output(
        [
            "git",
            "-c",
            f"safe.directory={root.as_posix()}",
            "show",
            f"{revision}:{relative}",
        ],
        cwd=root,
    ).decode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=BASELINE)
    parser.add_argument(
        "--output", type=Path, default=Path("tests/contracts/interfaces-23cb115.json")
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    records = []
    for old, new in module_pairs():
        source = baseline_source(root, args.baseline, old)
        raw = source.encode("utf-8")
        selection = "Settings" if old == "laomedo.skills.sources.settings" else "module"
        records.append(
            {
                "old_module": old,
                "new_module": new,
                "selection": selection,
                "source_git_blob": hashlib.sha1(
                    b"blob " + str(len(raw)).encode() + b"\0" + raw
                ).hexdigest(),
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "body_sha256": source_digest(source, selection=selection),
            }
        )
    records.append(
        {
            "old_module": "laomedo.skills.sources.settings",
            "new_module": "laomedo.skills.sources.settings",
            "selection": "fixed_source_policy",
            "body_sha256": source_digest(
                baseline_source(root, args.baseline, "laomedo.skills.sources.settings"),
                selection="fixed_source_policy",
            ),
        }
    )
    args.output.write_text(
        json.dumps(
            {
                "baseline": args.baseline,
                "derivation": "tools/capture_interface_contracts.py: exact Git source, named AST, remove imports/module docstring, collapse only actual Laomedo module aliases. Preserve bytes as typed hex, all constants, signatures, field defaults, routes, errors and other statements.",
                "modules": records,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
