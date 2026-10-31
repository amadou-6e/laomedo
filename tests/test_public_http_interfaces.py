"""Public adapter ownership, saved consumers and graph-template contracts."""

import ast
import importlib
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
INTERFACE_MODULE_PAIRS = tuple(
    (f"laomedo.{owner}.{feature}.{leaf}", f"laomedo.{owner}.interface.{feature}.{leaf}")
    for owner, feature in (
        ("github", "issues"),
        ("github", "pull_requests"),
        ("skills", "sources"),
        ("skills", "operations"),
    )
    for leaf in ("client", "handler", "server", "cli", "settings")
)
with patch.object(
    sys, "path", [str(ROOT / "tools"), str(ROOT / "tools/migrations"), *sys.path]
):
    MIGRATION = runpy.run_path(str(ROOT / "tools/migrations/migrate_module_paths.py"))


class PublicHttpInterfaceTests(unittest.TestCase):

    def test_maps_end_at_defining_interfaces_and_cli_commands_not_server_classes(self):
        self.assertFalse(
            set(MIGRATION["MODULE_PATHS"]) & set(MIGRATION["MODULE_PATHS"].values())
        )
        for old, new in INTERFACE_MODULE_PAIRS:
            if old == "laomedo.skills.sources.settings":
                self.assertNotIn(old, MIGRATION["MODULE_PATHS"])
                self.assertEqual(
                    MIGRATION["SYMBOL_PATHS"][old + ".Settings"], new + ".Settings"
                )
                self.assertFalse(hasattr(importlib.import_module(old), "Settings"))
            else:
                self.assertEqual(MIGRATION["MODULE_PATHS"][old], new)
                self.assertFalse(
                    ROOT.joinpath("src", *old.split(".")).with_suffix(".py").exists()
                )
                self.assertFalse(
                    any(
                        value == old or value.startswith(old + ".")
                        for value in MIGRATION["MODULE_PATHS"].values()
                    )
                )
        for group in (
            "github.issues",
            "github.pull_requests",
            "skills.sources",
            "skills.operations",
        ):
            owner, feature = group.split(".")
            old = f"laomedo.{group}.server"
            server = f"laomedo.{owner}.interface.{feature}.server"
            cli = f"laomedo.{owner}.interface.{feature}.cli"
            self.assertEqual(MIGRATION["MODULE_PATHS"][old], server)
            self.assertEqual(MIGRATION["CLI_PATHS"][old], cli)
            self.assertIn("-m " + cli, MIGRATION["migrate_source"]("python -m " + old))

    def test_example_patch_targets_and_viewer_commands_use_current_interfaces(self):
        """Cover bare literal patch calls and the source-service command in two viewer docs."""
        for path in ROOT.joinpath("examples").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                if not isinstance(node.func, ast.Name) or node.func.id != "patch":
                    continue
                target = node.args[0]
                if not isinstance(target, ast.Constant) or not isinstance(
                    target.value, str
                ):
                    continue
                for retired in MIGRATION["MODULE_PATHS"]:
                    self.assertFalse(
                        target.value.startswith(retired + "."), (path, target.value)
                    )
        current = "laomedo.skills.interface.sources.cli"
        for relative in (
            "frontend/langflow-skill-viewer/SOURCE-DEPLOYMENT.md",
            "frontend/langflow-skill-viewer/README.md",
        ):
            text = ROOT.joinpath(relative).read_text(encoding="utf-8")
            self.assertIn(current, text, relative)
            self.assertNotIn("laomedo.skills.sources.cli", text, relative)
        target = "laomedo.github.interface.pull_requests.client.pr_request"
        with patch(target) as request:
            from laomedo.github.interface.pull_requests.client import pr_request

            self.assertIs(pr_request, request)

    def test_partial_source_settings_migration_is_symbol_specific_and_fail_closed(self):
        old = "laomedo.skills.sources.settings"
        new = "laomedo.skills.interface.sources.settings"
        for source in (
            f"from {old} import Settings\nvalue = Settings()\n",
            f"import {old} as settings\nvalue = settings.Settings()\n",
            "from laomedo.skills.sources import settings\nvalue = settings.Settings()\n",
            f"from {old} import Settings, SKIP\nvalue = (Settings(), SKIP)\n",
        ):
            migrated = MIGRATION["migrate_source"](source)
            self.assertIn(new, migrated)
            self.assertEqual(MIGRATION["migrate_source"](migrated), migrated)
            if "Settings, SKIP" in source:
                self.assertIn(f"from {old} import SKIP", migrated)
                self.assertIn(f"from {new} import Settings", migrated)
        for source in (
            f"from {old} import *\n",
            f"import {old} as settings\nvalue = getattr(settings, 'Settings')\n",
            f"import {old} as settings\nvalue = getattr(settings, selected)\n",
            f"import {old}\nvalue = {old}.Settings()\n",
        ):
            with self.assertRaises(MIGRATION["ManualMigrationRequired"]):
                MIGRATION["migrate_source"](source)
        for source in (
            f"from {old} import SKIP\nvalue = SKIP\n",
            f"import {old} as settings\nvalue = settings.MAX_ENTRIES\n",
            f"import {old} as settings\nvalue = getattr(settings, 'SKIP')\n",
        ):
            self.assertEqual(MIGRATION["migrate_source"](source), source)

    def test_client_imports_are_leafs_and_cli_help_never_starts_a_service(self):
        script = """import importlib, pathlib, sys
root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root / 'src'))
for group in ('github.interface.issues', 'github.interface.pull_requests', 'skills.interface.sources', 'skills.interface.operations'):
    module = importlib.import_module('laomedo.' + group + '.client')
    if not pathlib.Path(module.__file__).resolve().is_relative_to(root):
        raise AssertionError(module.__file__)
for prefix in ('laomedo.host', 'laomedo.agents', 'langflow', 'lfx'):
    if any(name == prefix or name.startswith(prefix + '.') for name in sys.modules):
        raise AssertionError(prefix)
"""
        completed = subprocess.run(
            [sys.executable, "-c", script, str(ROOT)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        environment = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        for group in (
            "github.interface.issues",
            "github.interface.pull_requests",
            "skills.interface.sources",
            "skills.interface.operations",
        ):
            completed = subprocess.run(
                [sys.executable, "-m", "laomedo." + group + ".cli", "--help"],
                capture_output=True,
                text=True,
                timeout=60,
                env=environment,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("--api-token-file", completed.stdout)

    def test_changed_modules_use_direct_symbols_without_new_nested_classes(self):
        paths = [
            ROOT.joinpath("src", *new.split(".")).with_suffix(".py")
            for _, new in INTERFACE_MODULE_PAIRS
        ]
        for path in paths:
            tree = ast.parse(path.read_text())
            self.assertFalse(
                [
                    node
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Import)
                    and any(
                        item.name.startswith("laomedo.") and item.asname
                        for item in node.names
                    )
                ],
                path,
            )
            top = {id(node) for node in tree.body}
            self.assertFalse(
                [
                    node.name
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ClassDef) and id(node) not in top
                ],
                path,
            )
            self.assertFalse(
                any(isinstance(node, ast.ClassDef) for node in ast.walk(tree))
                and any(
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    for node in tree.body
                ),
                path,
            )

    def test_maintained_graph_tokens_migrate_without_altering_other_values(self):
        history = json.loads((ROOT / "examples/agent-module-history.json").read_text())
        immutable = {record["historical_original"] for record in history["files"]}
        immutable.update(
            {
                "examples/github-pr/original-agent/historical-flow-before-skill-input.json",
                "examples/skill-operations/historical-flow-before-skill-input.json",
            }
        )
        for path in (ROOT / "examples").rglob("*.json"):
            if path.relative_to(ROOT).as_posix() in immutable:
                continue
            source = path.read_text(encoding="utf-8-sig")
            self.assertEqual(MIGRATION["migrate_json_source"](source), source, path)

    def test_component_templates_follow_canonical_source_and_keep_graph_values(self):
        contract = json.loads(
            (ROOT / "tests/contracts/component-templates.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(contract["files"])
        for record in contract["files"]:
            graph = json.loads((ROOT / record["path"]).read_text(encoding="utf-8"))
            nodes = graph.get("nodes", graph.get("data", {}).get("nodes", []))
            for selected in record["nodes"]:
                matches = [
                    node for node in nodes if node.get("id") == selected["node_id"]
                ]
                self.assertEqual(len(matches), 1, (record["path"], selected["node_id"]))
                definition = matches[0]["data"]["node"]
                canonical = (ROOT / selected["component"]).read_text(encoding="utf-8")
                self.assertEqual(
                    definition["template"]["code"]["value"], canonical, record["path"]
                )
                if selected["has_code_hash"]:
                    self.assertEqual(
                        definition["metadata"]["code_hash"],
                        hashlib.sha256(canonical.encode()).hexdigest()[:12],
                    )
                    definition["metadata"]["code_hash"] = "CANONICAL_COMPONENT_HASH"
                definition["template"]["code"]["value"] = "CANONICAL_COMPONENT_SOURCE"
            encoded = json.dumps(
                graph, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
            self.assertEqual(
                hashlib.sha256(encoded).hexdigest(),
                record["graph_values_sha256"],
                record["path"],
            )

    def test_defining_error_guard_follows_current_interface_sources(self):
        source = (ROOT / "tests/test_http_handler_boundaries.py").read_text()
        for group in ("github", "skills"):
            self.assertIn(group + "/interface/", source)
        self.assertIn('SOURCE / "skills/interface/sources/handler.py"', source)
        source_policy = importlib.import_module("laomedo.skills.sources.settings")
        self.assertEqual(source_policy.MAX_ENTRIES, 4096)
        self.assertIn(".git", source_policy.SKIP)
        self.assertIn(".env", source_policy.SECRET)


if __name__ == "__main__":
    unittest.main()
