"""C2 ownership and import-only migration controls; no live integration claim."""

import ast
import hashlib
import importlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

from laomedo.host.mediation.store import MediationStore
from laomedo.host.publication.ingestion.errors import BundleIngestError

ROOT = Path(__file__).resolve().parents[1]
OWNER = "laomedo.host.publication.ingestion"
RETIRED = "laomedo.skills.ingestion"
RENAMES = {
    "_bound_roots": "validate_ingestion_roots",
    "_record": "read_run_binding",
    "_redirected": "is_redirected_path",
    "_durable_json": "write_durable_json",
    "_bundle_bytes": "read_bundle_bytes",
    "_IDENTITY": "RUN_IDENTITY",
}
sys.path.insert(0, str(ROOT / "tools/migrations"))
MIGRATION = runpy.run_path(str(ROOT / "tools/migrations/migrate_module_paths.py"))
CONTRACT_TOOLS = runpy.run_path(str(ROOT / "tools/capture_http_handler_contracts.py"))


class PublicationIngestionBoundaryTests(unittest.TestCase):
    @staticmethod
    def normalized(node):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in {"_ingestion_settings", "_ingestion_errors"}
        ):
            return ast.Name(id=RENAMES.get(node.attr, node.attr), ctx=ast.Load())
        if isinstance(node, ast.Name):
            node.id = RENAMES.get(node.id, node.id)
        if isinstance(node, ast.FunctionDef):
            node.name = RENAMES.get(node.name, node.name)
        for name, value in ast.iter_fields(node):
            if isinstance(value, list):
                setattr(
                    node,
                    name,
                    [
                        (
                            PublicationIngestionBoundaryTests.normalized(item)
                            if isinstance(item, ast.AST)
                            else item
                        )
                        for item in value
                    ],
                )
            elif isinstance(value, ast.AST):
                setattr(node, name, PublicationIngestionBoundaryTests.normalized(value))
        return node

    @staticmethod
    def retired_imports(source):
        failures = []
        for node in ast.walk(ast.parse(source)):
            names = (
                [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else (
                    [item.name for item in node.names]
                    if isinstance(node, ast.Import)
                    else []
                )
            )
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, (ast.Name, ast.Attribute))
                and (
                    node.func.id if isinstance(node.func, ast.Name) else node.func.attr
                )
                in {"__import__", "import_module"}
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                names.append(node.args[0].value)
            failures.extend(
                name
                for name in names
                if isinstance(name, str)
                and (name == RETIRED or name.startswith(RETIRED + "."))
            )
        return failures

    def test_ingestion_control_flow_and_serialization_are_an_exact_symbol_only_move(
        self,
    ):
        contract = json.loads(
            (ROOT / "tests/contracts/publication-ingestion-4551ce5.json").read_text()
        )
        self.assertEqual(
            contract["baseline"], "4551ce52524f6ec997f4df04a984f0c850170e55"
        )
        raw = contract["baseline_source"].encode()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), contract["sha256"])
        old = ast.parse(contract["baseline_source"])
        old.body = [
            item
            for item in old.body
            if not isinstance(item, (ast.Import, ast.ImportFrom))
        ]
        new = ast.parse(
            (ROOT / "src/laomedo/host/publication/ingestion/utils.py").read_text()
        )
        new.body = [
            item
            for item in new.body
            if not isinstance(item, (ast.Import, ast.ImportFrom))
        ]
        self.assertEqual(
            CONTRACT_TOOLS["ast_digest"](self.normalized(old)),
            CONTRACT_TOOLS["ast_digest"](new),
        )

    def test_ownership_symbols_and_all_prior_generations_are_flat(self):
        self.assertFalse((ROOT / "src/laomedo/skills/ingestion").exists())
        mapping = MIGRATION["MODULE_PATHS"]
        symbols = MIGRATION["SYMBOL_PATHS"]
        self.assertEqual(mapping[RETIRED], OWNER)
        self.assertFalse(set(mapping) & set(mapping.values()))
        for value in [*mapping.values(), *symbols.values()]:
            self.assertFalse(value == RETIRED or value.startswith(RETIRED + "."), value)
        for old, new in RENAMES.items():
            leaf = "settings" if old == "_IDENTITY" else "utils"
            self.assertEqual(
                symbols[f"{RETIRED}.{leaf}.{old}"], f"{OWNER}.{leaf}.{new}"
            )
            source = f"from {RETIRED}.{leaf} import {old}\nvalue = {old}\n"
            migrated = MIGRATION["migrate_source"](source)
            self.assertIn(f"from {OWNER}.{leaf} import {new} as {old}", migrated)
            self.assertEqual(MIGRATION["migrate_source"](migrated), migrated)
        module = importlib.import_module(OWNER + ".errors")
        error = module.BundleIngestError("run_binding_invalid")
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(
            (error.code, error.args), ("run_binding_invalid", ("run_binding_invalid",))
        )
        self.assertTrue(Path(module.__file__).resolve().is_relative_to(ROOT))

    def test_tracked_callers_have_no_retired_ingestion_imports(self):
        records = json.loads(
            (ROOT / "tools/migrations/retained-ingestion-callers.json").read_text()
        )["files"]
        preserved = {item["path"]: item["sha256"] for item in records}
        preserved.update(
            {
                item["path"]: item["sha256"]
                for item in json.loads(
                    (ROOT / "tools/formatting/historical-sources.json").read_text()
                )
            }
        )
        tracked = (
            subprocess.check_output(
                [
                    "git",
                    "-c",
                    f"safe.directory={ROOT.as_posix()}",
                    "ls-files",
                    "-z",
                    "--",
                    "*.py",
                ],
                cwd=ROOT,
            )
            .decode()
            .split("\0")
        )
        for relative in filter(None, tracked):
            path = ROOT / relative
            if not path.exists():
                continue  # Staged deletions are covered by the owner/map checks.
            if relative in preserved:
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    preserved[relative],
                    relative,
                )
                continue
            self.assertEqual(
                self.retired_imports(path.read_text(encoding="utf-8-sig")), [], relative
            )
        for source in [
            f"from {RETIRED}.utils import *",
            f"import {RETIRED}.utils as ingress",
            f"importlib.import_module('{RETIRED}.utils')",
            f"__import__('{RETIRED}.utils')",
        ]:
            self.assertTrue(self.retired_imports(source), source)

    def test_retained_probe_migration_changes_only_imports_and_leaves_bytes(self):
        records = json.loads(
            (ROOT / "tools/migrations/retained-ingestion-callers.json").read_text()
        )["files"]
        for item in records:
            path = ROOT / item["path"]
            raw = path.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), item["sha256"])
            source = raw.decode("utf-8")
            migrated = MIGRATION["migrate_source"](source)
            self.assertFalse(self.retired_imports(migrated))
            old, new = ast.parse(source), ast.parse(migrated)
            for tree in (old, new):
                tree.body = [
                    node
                    for node in tree.body
                    if not isinstance(node, (ast.Import, ast.ImportFrom))
                ]
            self.assertEqual(ast.dump(old), ast.dump(new), path)
            self.assertEqual(path.read_bytes(), raw)

    def test_helpers_have_no_domain_module_aliases_and_do_not_mix_objects(self):
        for relative in (
            "ingestion/utils.py",
            "ingestion/settings.py",
            "ingestion/errors.py",
            "verifier.py",
            "bundle/stage.py",
            "bundle/ownership.py",
            "verified/utils.py",
        ):
            tree = ast.parse(
                (ROOT / "src/laomedo/host/publication" / relative).read_text()
            )
            self.assertFalse(
                [
                    item
                    for item in tree.body
                    if isinstance(item, ast.Import)
                    and any(alias.name.startswith("laomedo.") for alias in item.names)
                ],
                relative,
            )
            self.assertFalse(
                any(isinstance(item, ast.ClassDef) for item in ast.walk(tree))
                and any(
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    for item in tree.body
                ),
                relative,
            )

    def test_ingestion_error_codes_follow_actual_host_and_mediation_boundaries(self):
        manifest = json.loads(
            (ROOT / "tests/contracts/publication-ingestion-errors.json").read_text()
        )
        tree = ast.parse(
            (ROOT / "src/laomedo/host/publication/ingestion/utils.py").read_text()
        )
        observed = {
            node.exc.args[0].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and isinstance(node.exc.func, ast.Name)
            and node.exc.func.id == "BundleIngestError"
            and node.exc.args
            and isinstance(node.exc.args[0], ast.Constant)
        }
        self.assertEqual(observed, set(manifest["ingestion_codes"]))
        exported = manifest["mediation_refusal_codes"]
        catalogue = json.loads(
            (
                ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
        self.assertFalse(set(exported) - catalogue.keys())
        self.assertEqual(
            set(manifest["unknown_exception_codes"]) | set(exported), observed
        )
        for code in exported:
            for field in ("title", "description", "recovery"):
                self.assertTrue(catalogue[code][field].strip(), (code, field))
        verified = ast.parse(
            (ROOT / "src/laomedo/host/publication/verified/utils.py").read_text()
        )
        extra = {
            node.exc.args[0].value
            for node in ast.walk(verified)
            if isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and isinstance(node.exc.func, ast.Name)
            and node.exc.func.id == "BundleIngestError"
            and node.exc.args
            and isinstance(node.exc.args[0], ast.Constant)
        }
        self.assertEqual(extra, set(manifest["additional_freezer_exception_codes"]))

    def test_mediation_preserves_four_refusals_and_collapses_raised_diagnostics(self):
        manifest = json.loads(
            (ROOT / "tests/contracts/publication-ingestion-errors.json").read_text()
        )
        with tempfile.TemporaryDirectory() as temporary:
            freezer = Mock()
            store = MediationStore(
                Path(temporary) / "effects.sqlite",
                now=lambda: 1000,
                monotonic=lambda: 100,
                stage_freezer=freezer,
            )
            _, token = store.issue(
                run_id="run-a",
                invocation_id="inv-a",
                repository="example/disposable",
                branch="run-branch",
                operations={"git_push"},
                ttl_seconds=60,
            )
            for code in manifest["mediation_refusal_codes"]:
                freezer.return_value = {"status": "refused", "reason": code}
                result = store.invoke(
                    token=token,
                    repository="example/disposable",
                    operation="bundle_freeze",
                    payload={"attempt_id": "attempt-a"},
                    effect_id=None,
                    transport=Mock(side_effect=AssertionError("no provider dispatch")),
                )
                self.assertEqual(result, {"state": "rejected", "error": code})
            for code in [
                *manifest["ingestion_codes"],
                *manifest["additional_freezer_exception_codes"],
            ]:
                freezer.side_effect = BundleIngestError(code)
                result = store.invoke(
                    token=token,
                    repository="example/disposable",
                    operation="bundle_freeze",
                    payload={"attempt_id": "attempt-a"},
                    effect_id=None,
                    transport=Mock(side_effect=AssertionError("no provider dispatch")),
                )
                self.assertEqual(result, {"state": "unknown", "resent": False})
            freezer.side_effect = RuntimeError("secret-control-not-for-projection")
            result = store.invoke(
                token=token,
                repository="example/disposable",
                operation="bundle_freeze",
                payload={"attempt_id": "attempt-a"},
                effect_id=None,
                transport=Mock(side_effect=AssertionError("no provider dispatch")),
            )
            self.assertNotIn("secret-control", json.dumps(result))
