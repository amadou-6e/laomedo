"""Curated provider application built on the API-only credential broker."""

from uuid import UUID
from copy import deepcopy

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

    async def admit_flow_write(
        self, request: Request, user=Depends(get_current_active_user)
    ):
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
            if payload.get("access_type") not in (None, "PRIVATE"):
                raise ValueError
            if payload.get("data") is not None:
                self.catalog.admission.effective_graph(payload["data"])
                # Native Flow persistence can also stage MCP credentials. Use
                # its pure extractor to refuse that effect before its writer.
                from langflow.api.utils.mcp.flow_secrets import (
                    extract_and_strip_mcp_secrets,
                    mcp_server_names,
                )

                carried, variables = extract_and_strip_mcp_secrets(
                    deepcopy(payload["data"])
                )
                if carried or variables or mcp_server_names(payload["data"]):
                    raise ValueError
            selected = request.path_params.get("flow_id")
            if selected is not None:
                from langflow.services.database.models.flow.model import Flow
                from langflow.services.deps import session_scope

                async with session_scope() as session:
                    existing = await session.get(Flow, UUID(str(selected)))
                    if existing is None or existing.user_id != UUID(str(user.id)):
                        raise ValueError
                    if any(
                        getattr(existing, field)
                        for field in (
                            "fs_path",
                            "mcp_enabled",
                            "a2a_enabled",
                            "webhook",
                            "is_component",
                        )
                    ):
                        raise ValueError
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
        source = self.profile_runtime.provider_source
        if source is not None:
            source = source.resolve()
            for private in (
                self.profile_runtime.admission.root,
                self.private_runtime.settings.runtime_root,
            ):
                private = private.resolve()
                if source.is_relative_to(private) or private.is_relative_to(source):
                    raise ValueError(
                        "Provider source must be separate from private runtime state."
                    )
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
