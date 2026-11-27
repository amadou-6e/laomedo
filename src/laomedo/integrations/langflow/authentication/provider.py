"""Curated provider application built on the API-only credential broker."""

from uuid import UUID

from fastapi import Depends, HTTPException, Request
from langflow.services.auth.utils import get_current_active_user

from laomedo.integrations.langflow.authentication.broker import PrivateBrokerRuntime
from laomedo.integrations.langflow.assistant.runtime import AssistantRuntime
from laomedo.integrations.langflow.assistant.settings import AssistantSettings
from laomedo.integrations.langflow.execution.providers.catalog import (
    ProviderComponentCatalog,
)
from laomedo.integrations.langflow.execution.providers.executor import (
    ProviderGraphExecutor,
)
from laomedo.integrations.langflow.execution.providers.settings import (
    ProviderAppSettings,
)


class ProviderBrowserRoutes:
    """Fixed metadata and pure-data Flow adapters, with no component execution APIs."""

    def __init__(self, catalog):
        self.catalog = catalog

    async def components(self, user=Depends(get_current_active_user)):
        """Return only fixed installed, owner-policy-filtered component metadata."""
        return (await self.catalog.for_owner(UUID(str(user.id)))).snapshot

    async def admit_flow_write(self, request: Request):
        """Refuse publication, filesystem bindings and untrusted code before persistence."""
        try:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 16 * 1024 * 1024:
                    raise ValueError
            import json

            payload = json.loads(body)
            if not isinstance(payload, dict) or any(
                payload.get(field)
                for field in (
                    "fs_path",
                    "mcp_enabled",
                    "a2a_enabled",
                    "webhook",
                    "is_component",
                    "endpoint_name",
                )
            ):
                raise ValueError
            if payload.get("data") is not None:
                self.catalog.admission.effective_graph(payload["data"])
        except Exception:
            raise HTTPException(
                422, detail={"code": "assistant_input_invalid"}
            ) from None

    def install(self, app):
        """Mount explicit safe handlers, never the native router or graph application."""
        from langflow.api.v1.endpoints import get_config, get_version
        from langflow.api.v1.flows import (
            read_flows,
            read_flow,
            create_flow,
            update_flow,
        )
        from langflow.api.v1.folders import router as folders

        app.add_api_route("/api/v1/all", self.components, methods=["GET"])
        app.add_api_route("/api/v1/config", get_config, methods=["GET"])
        app.add_api_route("/api/v1/version", get_version, methods=["GET"])
        for path in ("/api/v1/flows", "/api/v1/flows/"):
            app.add_api_route(path, read_flows, methods=["GET"])
            app.add_api_route(
                path,
                create_flow,
                methods=["POST"],
                dependencies=[Depends(self.admit_flow_write)],
            )
        app.add_api_route("/api/v1/flows/{flow_id}", read_flow, methods=["GET"])
        app.add_api_route(
            "/api/v1/flows/{flow_id}",
            update_flow,
            methods=["PATCH"],
            dependencies=[Depends(self.admit_flow_write)],
        )
        # The folder listing is data-only. No folder mutation/upload or native
        # component/template/validation/run route is mounted in this process.
        for route in folders.routes:
            if (
                getattr(route, "methods", set()) == {"GET"}
                and getattr(route, "path", None) == "/folders/"
            ):
                app.add_api_route("/api/v1/folders/", route.endpoint, methods=["GET"])


class ProviderBrokerRuntime(PrivateBrokerRuntime):
    """Opt-in catalog-only app: credentials and Python execution never co-reside.

    Ordinary custom-code Langflow deployments remain a separate mode. This app
    does not install native graph/template/editor/validation/MCP lifecycle APIs.
    Its only executable graph backend is the independently supervised worker.
    """

    def __init__(
        self, profile_runtime, private_settings, settings: ProviderAppSettings
    ):
        super().__init__(profile_runtime, private_settings)
        self.settings = settings

    def create_app(self):
        catalog = ProviderComponentCatalog(self.settings.components)
        app = super().create_app()
        executor = ProviderGraphExecutor(
            self.settings.worker, catalog, app.state.provider_connections.controllers
        )
        AssistantRuntime.install(
            app,
            catalog_loader=catalog.for_owner,
            graph_executor=executor,
            settings=AssistantSettings(app_url=self.private_runtime.settings.origin),
        )
        ProviderBrowserRoutes(catalog).install(app)
        from langflow.main import setup_static_files

        setup_static_files(app, self.settings.frontend)
        return app
