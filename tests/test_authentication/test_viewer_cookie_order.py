"""Verify the app factory's profile and private-cookie composition."""

from importlib.util import find_spec
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import sys
import unittest

if find_spec("fastapi") is None:
    raise unittest.SkipTest("Optional FastAPI runtime is not installed")

from fastapi import FastAPI

from laomedo.integrations.langflow.local_profiles.cookies import ProfileCookieBoundary
from laomedo.integrations.langflow.viewer import create_app


class PrivateMarker:
    """Stand in for private middleware while exercising the real app factory."""

    def __init__(self, app):
        self.app = app


class ProfileControl:
    def __init__(self):
        self.admission = SimpleNamespace(
            marker=SimpleNamespace(port=17867), root=Path.cwd()
        )

    def configure(self, app):
        pass


class PrivateControl:
    def __init__(self, settings):
        pass

    def configure(self, app):
        app.add_middleware(PrivateMarker)


class ViewerCookieOrderTests(unittest.TestCase):
    def test_factory_wraps_private_middleware_in_profile_cookie_boundary(self):
        main = ModuleType("langflow.main")
        main.create_app = FastAPI
        main.setup_static_files = lambda *args: None
        auth = ModuleType("langflow.services.auth.utils")
        auth.get_current_active_user = lambda: None
        mcp = ModuleType("laomedo.integrations.langflow.mcp_graph")
        mcp.McpGraphPolicy = SimpleNamespace(install=lambda: None)
        registry = ModuleType("laomedo.agents.mcp.registry")
        registry.McpRegistry = SimpleNamespace(install=lambda *args: None)
        assistant = ModuleType("laomedo.integrations.langflow.assistant.runtime")
        assistant.AssistantRuntime = SimpleNamespace(install=lambda *args: None)
        private = ModuleType("laomedo.integrations.langflow.authentication.runtime")
        private.PrivateBrowserRuntime = PrivateControl
        modules = {
            "langflow.main": main,
            "langflow.services.auth.utils": auth,
            "laomedo.integrations.langflow.mcp_graph": mcp,
            "laomedo.agents.mcp.registry": registry,
            "laomedo.integrations.langflow.assistant.runtime": assistant,
            "laomedo.integrations.langflow.authentication.runtime": private,
        }
        settings = SimpleNamespace(required_path=lambda name: str(Path.cwd()))
        with (
            patch.dict(sys.modules, modules),
            patch(
                "laomedo.integrations.langflow.viewer.Settings", return_value=settings
            ),
            patch("laomedo.integrations.langflow.viewer.install_routes"),
        ):
            app = create_app(profile_runtime=ProfileControl(), private_connections=True)

        self.assertIs(app.user_middleware[0].cls, ProfileCookieBoundary)
        self.assertIs(app.user_middleware[1].cls, PrivateMarker)
