"""Protect the cohesive activity package API."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class AgentActivityPackageTests(unittest.TestCase):
    def test_package_exports_store_api(self):
        from laomedo.activity import agent_activity
        import laomedo.activity.agent_activity.store as store
        from laomedo.activity.agent_activity import utils
        self.assertIs(agent_activity.ActivityStore, store.ActivityStore)
        for name in ("capture_for", "now"):
            self.assertIs(getattr(agent_activity, name), getattr(utils, name))

    def test_capture_uses_canonical_globals(self):
        from laomedo.activity.agent_activity.capture import RunnerCapture
        component = SimpleNamespace(runner_url="http://localhost:1", timeout_seconds=1)
        with patch("laomedo.activity.agent_activity.utils.capture_for", return_value=None):
            self.assertIsNone(RunnerCapture(component).capture)
