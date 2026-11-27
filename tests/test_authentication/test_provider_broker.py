"""Curated provider app wiring; this is not live container/model acceptance."""

import json
from importlib.util import find_spec
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch
from types import SimpleNamespace
from contextlib import asynccontextmanager

if find_spec("langflow") is None or find_spec("httpx") is None:
    raise unittest.SkipTest("Optional native Langflow HTTP runtime is not installed")

from httpx import ASGITransport, AsyncClient
from starlette.requests import Request
from langflow.services.auth.utils import get_current_active_user

from laomedo.integrations.langflow.authentication.provider import (
    ProviderBrokerRuntime,
    ProviderBrowserRoutes,
)
from laomedo.integrations.langflow.authentication.settings import PrivateBrowserSettings
from laomedo.integrations.langflow.execution.providers.settings import (
    ProviderAppSettings,
)
from laomedo.integrations.langflow.execution.worker.settings import GraphWorkerSettings
from laomedo.integrations.langflow.graph_admission.catalog import GitHubGraphCatalog
from laomedo.integrations.langflow.local_profiles.cookies import ProfileCookieBoundary


class ProviderBrokerTests(unittest.IsolatedAsyncioTestCase):
    """The account host has no native Python construction or execution endpoints."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.root = root
        (root / "assets").mkdir()
        (root / "index.html").write_text("<html>Curated provider app</html>")
        profile = Mock()
        profile.provider_source = None
        profile.admission.root = root / "profile-state"
        profile.configure.side_effect = self.configure_profile
        self.catalog = Mock()
        self.catalog.for_owner = AsyncMock()
        self.stack = []
        for target in (
            "laomedo.integrations.langflow.authentication.broker.PrivateBrowserRuntime",
            "laomedo.integrations.langflow.authentication.broker.get_rate_limiter",
            "laomedo.integrations.langflow.authentication.provider.ProviderComponentCatalog",
            "laomedo.integrations.langflow.authentication.provider.ProviderGraphExecutor",
        ):
            current = patch(target)
            self.stack.append(current.start())
            self.addCleanup(current.stop)
        private = PrivateBrowserSettings(
            origin="http://127.0.0.1:17885", runtime_root=root / "private"
        )
        self.stack[0].return_value.settings = private
        self.stack[2].return_value = self.catalog
        self.app = ProviderBrokerRuntime(
            profile,
            private,
            ProviderAppSettings(
                components=root,
                frontend=root,
                worker=GraphWorkerSettings(
                    image_id="sha256:" + "a" * 64, lease_state=root
                ),
            ),
        ).create_app()
        self.app.dependency_overrides[get_current_active_user] = self.authenticated

    async def authenticated(self):
        from uuid import uuid4

        return SimpleNamespace(id=uuid4())

    def configure_profile(self, app):
        app.state.provider_connections = SimpleNamespace(controllers=Mock())
        app.add_middleware(ProfileCookieBoundary, port=17885)

    def test_source_workspace_cannot_include_private_runtime_or_account_state(self):
        profile = Mock()
        profile.admission.root = self.root / "profile-state"
        private = self.stack[0].return_value.settings
        settings = ProviderAppSettings(
            components=private.runtime_root.parent,
            frontend=private.runtime_root.parent,
            worker=GraphWorkerSettings(
                image_id="sha256:" + "a" * 64, lease_state=private.runtime_root.parent
            ),
        )
        for source in (
            profile.admission.root,
            profile.admission.root / "provider-runs",
            profile.admission.root.parent,
        ):
            profile.provider_source = source
            with self.subTest(source=source), self.assertRaises(ValueError):
                ProviderBrokerRuntime(profile, private, settings).create_app()

    def test_source_export_refuses_environment_files_and_repository_metadata(self):
        source = self.root / "clean-export"
        source.mkdir()
        (source / "module.py").write_text("# tracked source")
        ProviderBrokerRuntime.admit_source(source)
        for name in (".env", ".env.local", ".git"):
            with self.subTest(name=name):
                forbidden = source / name
                forbidden.write_text("fixture only")
                try:
                    with self.assertRaises(ValueError):
                        ProviderBrokerRuntime.admit_source(source)
                finally:
                    forbidden.unlink()

    async def test_python_and_native_execution_apis_are_absent_in_credential_process(
        self,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=self.app), base_url="http://127.0.0.1:17885"
        ) as client:
            response = await client.get("/api/v1/custom_component/update")
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json(), {"detail": "Not Found"})
            response = await client.get("/api/v1/flows/basic_examples/")
            self.assertEqual(response.json(), [])
            response = await client.get("/api/v1/auto_login")
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json(), {"detail": {"auto_login": False}})
            for path in (
                "/api/v1/build/flow/flow",
                "/api/v1/validate/code",
                "/api/v1/custom_component",
                "/api/v1/custom_component/update",
                "/api/v1/run/flow",
            ):
                response = await client.post(path, json={"code": "never executed"})
                self.assertIn(response.status_code, (404, 405), path)
            response = await client.post(
                "/api/v2/workflows", json={"code": "never executed"}
            )
            self.assertIn(response.status_code, (401, 403, 422))
        self.assertIs(
            self.app.state.laomedo_assistant.graph_executor, self.stack[3].return_value
        )
        self.assertEqual(
            self.app.state.laomedo_assistant.catalog_loader, self.catalog.for_owner
        )

    @asynccontextmanager
    async def stored_flow(self):
        yield SimpleNamespace(get=AsyncMock(return_value=self.flow))

    async def test_existing_filesystem_flow_cannot_trigger_native_storage_write(self):
        from fastapi import HTTPException
        from uuid import uuid4
        from langflow.services.database.models.flow.model import Flow

        owner, identifier = uuid4(), uuid4()
        self.flow = Flow(
            id=identifier, user_id=owner, name="Managed flow", fs_path="managed.json"
        )
        request = await self.request({"name": "Edited name"})
        request.scope["path_params"] = {"flow_id": str(identifier)}
        with patch("langflow.services.deps.session_scope", new=self.stored_flow):
            with self.assertRaises(HTTPException):
                await ProviderBrowserRoutes(self.catalog).admit_flow_write(
                    request, SimpleNamespace(id=owner)
                )

    async def request(self, payload):
        body = json.dumps(payload).encode()

        async def receive():
            return {"type": "http.request", "body": body}

        return Request(
            {"type": "http", "method": "PATCH", "path": "/api/v1/flows/fixture"},
            receive=receive,
        )

    async def test_flow_writes_cannot_import_custom_code_or_enable_host_publication(
        self,
    ):
        from fastapi import HTTPException

        source = "raise AssertionError('must not execute')"
        catalog = GitHubGraphCatalog.capture(
            {"io": {"TextInput": {"template": {"code": {"value": source}}}}}
        )
        boundary = ProviderBrowserRoutes(SimpleNamespace(admission=catalog))
        graph = {
            "nodes": [
                {
                    "id": "text",
                    "data": {
                        "id": "text",
                        "type": "TextInput",
                        "node": {"template": {"code": {"value": source}}},
                    },
                }
            ],
            "edges": [],
        }
        await boundary.admit_flow_write(await self.request({"data": graph}))
        graph["nodes"][0]["data"]["node"]["template"]["mcp_server"] = {
            "value": {
                "name": "fixture-server",
                "config": {"headers": {"Authorization": "fixture-only"}},
            }
        }
        with self.assertRaises(HTTPException):
            await boundary.admit_flow_write(await self.request({"data": graph}))
        graph["nodes"][0]["data"]["node"]["template"].pop("mcp_server")
        graph["nodes"][0]["data"]["node"]["template"]["code"]["value"] += "\n# forged"
        with self.assertRaises(HTTPException):
            await boundary.admit_flow_write(await self.request({"data": graph}))
        for field in (
            "fs_path",
            "mcp_enabled",
            "a2a_enabled",
            "webhook",
            "is_component",
            "endpoint_name",
        ):
            with self.subTest(field=field), self.assertRaises(HTTPException):
                await boundary.admit_flow_write(
                    await self.request({field: "unexpected"})
                )
