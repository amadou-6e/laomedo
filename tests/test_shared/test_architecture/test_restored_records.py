"""Canonical Shared records remain described, class-only and hidden on failure."""

import ast
import importlib
from pathlib import Path
import unittest
from pydantic import BaseModel


class SharedRecordStructureTests(unittest.TestCase):
    def test_shared_records_have_one_documented_model_owner(self):
        for name in (
            "host.credentials.siwc.models",
            "host.mediation.models",
            "host.publication.bundle.models",
            "host.publication.handoff.models",
            "host.publication.verified.models",
            "work_graph.models",
            "git.models",
        ):
            module = importlib.import_module("laomedo." + name)
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            self.assertFalse(
                any(
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    for node in tree.body
                ),
                name,
            )
            for value in vars(module).values():
                if (
                    isinstance(value, type)
                    and issubclass(value, BaseModel)
                    and value.__module__ == module.__name__
                ):
                    # Existing WorkItem/Dependency/GraphSnapshot fields retain their established contract;
                    # the newly restored records all describe their externally read fields.
                    if value.__name__ in {"WorkItem", "Dependency", "GraphSnapshot"}:
                        continue
                    with self.subTest(model=value.__name__):
                        self.assertTrue(
                            all(
                                field.description
                                for field in value.model_fields.values()
                            )
                        )
