"""Reproduce C1 controls from exact Git source without running its live services.

Run with --baseline REV --output tests/contracts/http-handlers-4228872.json.
The fixture retains exact original source/blob identity. Tests derive its normalized
control independently on each supported Python version before comparing handlers.
"""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess

BASELINE = "422887273038523ca6343234739775b1d218b673"
BINDINGS = {
    "github/issues": "gateway",
    "github/pull_requests": "gateway",
    "skills/sources": "sources",
    "skills/operations": "operations",
}
ALIASES = {
    "_issues_contract",
    "_pull_requests_contract",
    "_mediation_errors",
    "_sources_errors",
}


def canonical_ast(value):
    """Keep all AST fields except version-only empty type-parameter metadata.

    Unlike ast.dump, this JSON representation is independent of field order and
    show_empty defaults. Nonempty type parameters and every other empty/None
    field stay meaningful. No source positions are included.
    """
    if isinstance(value, ast.AST):
        return {
            "node": type(value).__name__,
            "fields": {
                name: canonical_ast(field)
                for name, field in ast.iter_fields(value)
                if not (name == "type_params" and field == [])
            },
        }
    if isinstance(value, list):
        return [canonical_ast(item) for item in value]
    return value


def ast_digest(node):
    """Hash the version-independent, fully named AST field representation."""
    raw = json.dumps(
        canonical_ast(node), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def bind_original(node, service):
    """Only replace closure bindings and the four recorded module aliases."""
    if isinstance(node, ast.Name) and node.id in {service, "token"}:
        return ast.Attribute(
            value=ast.Attribute(
                value=ast.Name(id="self", ctx=ast.Load()), attr="server", ctx=ast.Load()
            ),
            attr="_token" if node.id == "token" else node.id,
            ctx=ast.Load(),
        )
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in ALIASES
    ):
        return ast.Name(id=node.attr, ctx=ast.Load())
    for name, value in ast.iter_fields(node):
        if isinstance(value, list):
            setattr(
                node,
                name,
                [
                    bind_original(item, service) if isinstance(item, ast.AST) else item
                    for item in value
                ],
            )
        elif isinstance(value, ast.AST):
            setattr(node, name, bind_original(value, service))
    return node


def normalized_handler(node):
    """Ignore only the extracted class name and its new class-level docstring."""
    node.name = "Handler"
    if ast.get_docstring(node):
        node.body.pop(0)
    return node


def contract_for_source(source, service):
    """Derive a contract from the retained ORIGINAL server, never a new handler."""
    tree = ast.parse(source)
    owner = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    init = next(node for node in owner.body if isinstance(node, ast.FunctionDef))
    handler = next(node for node in init.body if isinstance(node, ast.ClassDef))
    admission = next(node for node in init.body if isinstance(node, ast.If))
    raw = source.encode("utf-8")
    return {
        "service_binding": service,
        "source_git_blob": hashlib.sha1(
            b"blob " + str(len(raw)).encode() + b"\0" + raw
        ).hexdigest(),
        "baseline_source": source,
        "handler_ast_sha256": ast_digest(
            normalized_handler(bind_original(handler, service))
        ),
        "admission_ast_sha256": ast_digest(admission),
        "arguments_ast_sha256": ast_digest(init.args),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=BASELINE)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/contracts/http-handlers-4228872.json"),
    )
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    records = {}
    for relative, service in BINDINGS.items():
        source = subprocess.check_output(
            [
                "git",
                "-c",
                f"safe.directory={root.as_posix()}",
                "show",
                f"{arguments.baseline}:src/laomedo/{relative}/server.py",
            ],
            cwd=root,
        ).decode("utf-8")
        records[relative] = contract_for_source(source, service)
    payload = {
        "baseline": arguments.baseline,
        "canonicalization": "Named AST fields; omit only empty type_params; bind only captured service/token and recorded module aliases; ignore class name/docstring.",
        "handlers": records,
    }
    arguments.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
