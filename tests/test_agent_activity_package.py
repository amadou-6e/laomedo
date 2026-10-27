"""Protect the grouped activity package and original flat imports."""
import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class AgentActivityPackageTests(unittest.TestCase):
    def test_legacy_imports_resolve_to_canonical_modules(self):
        for suffix, leaf in (("", "store"), ("_capture", "capture"),
                             ("_cost", "cost"), ("_projection", "projection"),
                             ("_routes", "routes")):
            with self.subTest(module=leaf):
                try:
                    canonical = importlib.import_module("laomedo.activity.agent_activity." + leaf)
                except ModuleNotFoundError as error:
                    if leaf == "routes" and (error.name or "").split(".")[0] in {"fastapi", "starlette"}:
                        self.skipTest("Optional activity API dependencies are not installed")
                    raise
                self.assertIs(importlib.import_module("laomedo.agent_activity" + suffix), canonical)

    def test_package_exports_the_existing_store_api(self):
        from laomedo.activity import agent_activity
        from laomedo.activity.agent_activity import store
        for name in ("ActivityStore", "capture_for", "now"):
            self.assertIs(getattr(agent_activity, name), getattr(store, name))

    def test_old_capture_patch_reaches_canonical_capture_globals(self):
        from laomedo.activity.agent_activity.capture import RunnerCapture
        with patch("laomedo.agent_activity_capture.capture_for", return_value=None):
            component = SimpleNamespace(runner_url="http://localhost:1", timeout_seconds=1)
            self.assertIsNone(RunnerCapture(component).capture)


if __name__ == "__main__":
    unittest.main()
