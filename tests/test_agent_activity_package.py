"""Protect the cohesive activity package API."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class AgentActivityPackageTests(unittest.TestCase):
    def test_package_exports_store_api(self):
        from laomedo.activity import agent_activity
        from laomedo.activity.agent_activity import store
        for name in ("ActivityStore", "capture_for", "now"):
            self.assertIs(getattr(agent_activity, name), getattr(store, name))

    def test_capture_uses_canonical_globals(self):
        from laomedo.activity.agent_activity.capture import RunnerCapture
        component = SimpleNamespace(runner_url="http://localhost:1", timeout_seconds=1)
        with patch("laomedo.activity.agent_activity.capture.capture_for", return_value=None):
            self.assertIsNone(RunnerCapture(component).capture)
