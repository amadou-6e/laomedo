"""Curated provider app wiring; this is not live container/model acceptance."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch
from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

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


class ProviderBrokerTests(unittest.IsolatedAsyncioTestCase):
    """The account host has no native Python construction or execution endpoints."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / "assets").mkdir()
        (root / "index.html").write_text("<html>Curated provider app</html>")
        profile = Mock()
        profile.configure.side_effect = lambda app: setattr(
            app.state, "provider_connections", SimpleNamespace(controllers=Mock())
        )
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

    async def test_python_and_native_execution_apis_are_absent_in_credential_process(
        self,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=self.app), base_url="http://127.0.0.1:17885"
        ) as client:
            for path in (
                "/api/v1/build/flow/flow",
                "/api/v1/validate/code",
                "/api/v1/custom_component",
                "/api/v1/custom_component/update",
                "/api/v1/run/flow",
                "/api/v2/workflows",
            ):
                response = await client.post(path, json={"code": "never executed"})
                self.assertIn(response.status_code, (404, 405), path)
        self.assertIs(
            self.app.state.laomedo_assistant.graph_executor, self.stack[3].return_value
        )
        self.assertEqual(
            self.app.state.laomedo_assistant.catalog_loader, self.catalog.for_owner
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
