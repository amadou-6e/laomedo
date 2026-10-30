"""Keep migrated domain callers on defining symbols and preserve lazy boundaries."""

import ast
from pathlib import Path
import unittest


class DefiningImportTests(unittest.TestCase):
    def test_migrated_callers_do_not_reintroduce_feature_module_prefixes(self):
        source = Path(__file__).resolve().parents[1] / "src/laomedo"
        paths = (
            "host/credentials/siwc/browser.py",
            "host/credentials/siwc/cli.py",
            "host/credentials/siwc/utils.py",
            "host/leases/client.py",
            "host/leases/process.py",
            "host/leases/process_cli.py",
            "host/leases/service_cli.py",
            "host/leases/utils.py",
            "host/managed_service.py",
            "host/publication/bundle/settings.py",
            "host/publication/cli.py",
            "host/publication/controller.py",
            "host/publication/handoff/utils.py",
            "host/runner/routes.py",
            "host/runner/service.py",
            "host/runner/utils.py",
            "work_graph/stage_worker.py",
        )
        for relative in paths:
            with self.subTest(module=relative):
                tree = ast.parse((source / relative).read_text(encoding="utf-8-sig"))
                offenders = [
                    (node.lineno, item.name)
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Import)
                    for item in node.names
                    if item.name.startswith("laomedo.")
                ]
                self.assertEqual(offenders, [], "Import the defining object directly")

    def test_lazy_composition_imports_are_not_lifted_to_module_scope(self):
        source = Path(__file__).resolve().parents[1] / "src/laomedo"
        sites = (
            (
                "host/credentials/siwc/browser.py",
                "browser_connect",
                "laomedo.host.credentials.siwc.connection",
            ),
            (
                "host/credentials/siwc/cli.py",
                "main",
                "laomedo.host.credentials.siwc.connection",
            ),
            (
                "host/credentials/siwc/utils.py",
                "_https_json",
                "laomedo.host.credentials.siwc.connection",
            ),
            (
                "host/credentials/siwc/utils.py",
                "_revoke",
                "laomedo.host.credentials.siwc.connection",
            ),
            (
                "host/runner/routes.py",
                "install_runner_service_routes",
                "laomedo.host.runner.service",
            ),
            ("host/managed_service.py", "main", "laomedo.host.host_services"),
            ("host/managed_service.py", "main", "laomedo.host.publication.cli"),
        )
        for relative, function, module in sites:
            with self.subTest(module=relative, function=function, dependency=module):
                tree = ast.parse((source / relative).read_text(encoding="utf-8-sig"))
                owner = next(
                    node
                    for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == function
                )
                self.assertTrue(
                    any(
                        isinstance(node, ast.ImportFrom) and node.module == module
                        for node in ast.walk(owner)
                    )
                )
                self.assertFalse(
                    any(
                        isinstance(node, ast.ImportFrom) and node.module == module
                        for node in tree.body
                    )
                )
