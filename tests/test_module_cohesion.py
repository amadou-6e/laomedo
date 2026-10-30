"""Structural policy and published migration reachability, not live acceptance."""

import ast
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "laomedo"


class ModuleCohesionTests(unittest.TestCase):
    def test_production_imports_use_defining_symbols_instead_of_modules(self):
        """Resolve from-imports too, so package imports cannot hide module aliases."""
        violations = []
        for path in SOURCE.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [
                        item.name
                        for item in node.names
                        if item.name.startswith("laomedo.")
                    ]
                elif (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and node.module.startswith("laomedo.")
                ):
                    for item in node.names:
                        member = ROOT.joinpath(
                            "src", *node.module.split("."), item.name
                        )
                        if (
                            member.with_suffix(".py").is_file()
                            or (member / "__init__.py").is_file()
                        ):
                            modules.append(node.module + "." + item.name)
                violations.extend(
                    f"{path.relative_to(SOURCE).as_posix()}:{node.lineno}:{module}"
                    for module in modules
                )
        self.assertEqual(violations, [], "Import each symbol from its defining module")

    def test_production_classes_are_not_declared_inside_functions(self):
        """Guard maintained implementation directories, not historical probes.

        Experiments, retained probes and inherited test/example doubles are
        deliberately outside this production guard; no historical-clean claim.
        """
        nested = []
        for directory in (ROOT / "src", ROOT / "components", ROOT / "tools"):
            for path in directory.rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8-sig"))
                parents = {
                    child: node
                    for node in ast.walk(tree)
                    for child in ast.iter_child_nodes(node)
                }
                for node in ast.walk(tree):
                    if not isinstance(node, ast.ClassDef):
                        continue
                    ancestor = parents.get(node)
                    while ancestor is not None:
                        if isinstance(
                            ancestor, (ast.FunctionDef, ast.AsyncFunctionDef)
                        ):
                            nested.append(
                                f"{path.relative_to(ROOT).as_posix()}:{node.lineno}:{node.name}"
                            )
                            break
                        ancestor = parents.get(ancestor)
        self.assertEqual(nested, [], "Move implementation classes to module scope")

    def test_historical_execution_graph_blobs_are_preserved_beside_templates(self):
        manifest = json.loads(
            (ROOT / "examples/agent-module-history.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            manifest["baseline"], "8e2a2925c74748672f3028ba09359c49b13e1635"
        )
        self.assertEqual(len(manifest["files"]), 7)
        for record in manifest["files"]:
            original = ROOT / record["historical_original"]
            self.assertTrue(record["immutable"])
            raw = original.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), record["sha256"])
            header = b"blob " + str(len(raw)).encode("ascii") + b"\0"
            self.assertEqual(hashlib.sha1(header + raw).hexdigest(), record["git_blob"])

    def test_historical_graph_inputs_keep_their_original_bytes(self):
        # Baseline:6069ac99998af97acd314bb2c56c08d4bc2c3f29; migrate copies only.
        expected = {
            "examples/github-pr/original-agent/historical-flow-before-skill-input.json": "3584ef1108f5be5ddc5b0f7a6f583044fcf31f769874d5368ec86772c63b6b4f",
            "examples/skill-operations/historical-flow-before-skill-input.json": "45ea8e14f22dc52e50e97d367812ad832deb048e1e31e9c58bff8b48c62879cf",
        }
        for relative, digest in expected.items():
            self.assertEqual(
                hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(),
                digest,
                relative,
            )

    def test_symbol_map_targets_have_a_declared_definition_or_submodule(self):
        targets = set(
            json.loads(
                (ROOT / "tools/migrations/symbol-paths.json").read_text()
            ).values()
        )
        for target in targets:
            if not target.startswith("laomedo."):
                continue
            full = ROOT.joinpath("src", *target.split("."))
            if full.with_suffix(".py").is_file() or (full / "__init__.py").is_file():
                continue  # from package import submodule
            module, symbol = target.rsplit(".", 1)
            path = ROOT.joinpath("src", *module.split("."))
            path = (
                path.with_suffix(".py")
                if path.with_suffix(".py").exists()
                else path / "__init__.py"
            )
            self.assertTrue(path.is_file(), target)
            bindings = set()
            for node in ast.parse(path.read_text(encoding="utf-8-sig")).body:
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    bindings.add(node.name)
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    bindings.update(
                        item.asname
                        or (
                            item.name.split(".")[0]
                            if isinstance(node, ast.Import)
                            else item.name
                        )
                        for item in node.names
                    )
                elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                    for assigned in (
                        node.targets if isinstance(node, ast.Assign) else [node.target]
                    ):
                        bindings.update(
                            item.id
                            for item in ast.walk(assigned)
                            if isinstance(item, ast.Name)
                        )
            self.assertIn(symbol, bindings, target)

    def test_files_introduce_classes_or_standalone_functions(self):
        mixed = []
        for path in SOURCE.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            classes = any(isinstance(node, ast.ClassDef) for node in ast.walk(tree))
            functions = any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                for node in tree.body
            )
            if classes and functions:
                mixed.append(path.relative_to(SOURCE).as_posix())
        self.assertEqual(
            mixed, [], "Move helpers to methods or the owning feature function modules"
        )

    def test_a_module_never_shadows_a_feature_package(self):
        for path in SOURCE.rglob("*.py"):
            if path.name != "__init__.py":
                self.assertFalse(
                    (path.with_suffix("") / "__init__.py").exists(), str(path)
                )

    def test_distinct_feature_imports_never_rebind_the_same_module_alias(self):
        for path in SOURCE.rglob("*.py"):
            aliases = {}
            for node in ast.parse(path.read_text(encoding="utf-8-sig")).body:
                if not isinstance(node, ast.Import):
                    continue
                for item in node.names:
                    if item.asname:
                        self.assertFalse(
                            item.asname.startswith("__"),
                            "Module aliases must not trigger class name mangling: "
                            + str(path),
                        )
                        aliases.setdefault(item.asname, set()).add(item.name)
            self.assertFalse(
                {alias: names for alias, names in aliases.items() if len(names) > 1},
                str(path),
            )

    def test_every_published_module_generation_reaches_a_final_owner(self):
        mapping = json.loads((ROOT / "tools/migrations/module-paths.json").read_text())
        self.assertFalse(
            set(mapping) & set(mapping.values()), "Migration must finish in one pass"
        )
        for old, new in mapping.items():
            path = ROOT.joinpath("src", *new.split("."))
            self.assertTrue(
                path.with_suffix(".py").is_file() or (path / "__init__.py").is_file(),
                (old, new),
            )
