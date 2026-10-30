"""Prevent regressions in the migrated record ownership boundaries."""

import ast
import importlib
from pathlib import Path
import unittest
from pydantic import BaseModel


class StructuredRecordStructureTests(unittest.TestCase):
    def test_models_are_class_only_and_fields_are_described(self):
        modules = (
            "github.issues.models", "github.pull_requests.models",
            "skills.registry.models", "skills.operations.models",
            "agents.artifacts.models", "agents.orchestration.models",
            "agents.agents.base.models", "agents.interface.models",
        )
        for name in modules:
            module = importlib.import_module("laomedo." + name)
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            with self.subTest(module=name):
                self.assertFalse(any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in tree.body))
                for value in vars(module).values():
                    if isinstance(value, type) and issubclass(value, BaseModel) and value.__module__ == module.__name__:
                        for field in value.model_fields.values():
                            self.assertTrue(field.description, f"{value.__name__} has an undescribed field")

    def test_interface_models_remain_a_dependency_leaf(self):
        from laomedo.agents.interface import models
        tree = ast.parse(Path(models.__file__).read_text(encoding="utf-8"))
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertFalse(any(name.startswith("laomedo.") for name in imports))

    def test_component_keeps_its_module_docstring(self):
        from laomedo.agents.agents.base import agent
        source = Path(agent.__file__).parents[2] / "interface/langflow/component.py"
        self.assertIsNotNone(ast.get_docstring(ast.parse(source.read_text(encoding="utf-8"))))

    def test_join_handler_is_module_level_and_old_giant_constructors_stay_removed(self):
        from laomedo.integrations.langflow.join import server
        from laomedo.agents.agents.base import agent
        from laomedo.agents.orchestration import utils
        for module in (server, agent, utils):
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.assertFalse(any(isinstance(child, ast.ClassDef) for child in ast.walk(node)))
                    if node.name in {"_prepare", "envelope"}:
                        self.assertFalse(any(isinstance(child, ast.Dict) and len(child.keys) >= 10 for child in ast.walk(node)))
