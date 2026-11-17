"""Opt-in profile runtime composition; existing preview creation stays unchanged."""

from contextlib import asynccontextmanager

from langflow.services.deps import get_auth_service, get_settings_service
from lfx.services.manager import get_service_manager
from lfx.services.schema import ServiceType

from laomedo.integrations.langflow.local_profiles.admission import (
    ProfileRuntimeAdmission,
)
from laomedo.integrations.langflow.local_profiles.auth import LocalProfileAuthService
from laomedo.integrations.langflow.local_profiles.boundary import LocalProfileBoundary
from laomedo.integrations.langflow.local_profiles.cookies import ProfileCookieBoundary
from laomedo.integrations.langflow.local_profiles.errors import ProfileError
from laomedo.integrations.langflow.local_profiles.registry import LocalProfileRegistry
from laomedo.integrations.langflow.local_profiles.routes import router


class LocalProfileRuntime:
    """Admit before migration and verify the final service before accepting traffic."""

    def __init__(self, runtime_root, *, provider_source=None):
        self.admission = ProfileRuntimeAdmission(runtime_root)
        self.provider_source = provider_source
        self._upstream_lifespan = None

    def configure(self, app):
        """Install profile-only routes before the caller mounts the SPA fallback."""
        self.admission.prepare(get_settings_service())
        app.state.local_profiles_enabled = True
        app.state.local_profile_registry = LocalProfileRegistry()
        from laomedo.host.provider_connections.service import ProviderConnections
        from laomedo.integrations.langflow.provider_connections.routes import (
            install_provider_routes,
        )
        from laomedo.integrations.langflow.provider_connections.boundary import (
            ProviderSessionBoundary,
        )
        from langflow.services.auth.utils import get_current_active_user

        providers = ProviderConnections(self.admission.root / "provider-connections")
        from laomedo.host.provider_connections.controllers import ProviderControllers

        ProviderControllers(
            providers,
            self.admission.root / "provider-runs",
            self.admission.root / "registry",
            self.provider_source,
        )
        app.state.provider_connections = providers
        install_provider_routes(
            app,
            providers,
            get_current_active_user,
            origin=f"http://127.0.0.1:{self.admission.marker.port}",
        )
        app.add_middleware(ProviderSessionBoundary, service=providers)
        app.include_router(router)
        app.add_middleware(LocalProfileBoundary, port=self.admission.marker.port)
        # Last-added middleware is outermost: translate before all cookie users.
        app.add_middleware(ProfileCookieBoundary, port=self.admission.marker.port)
        self._upstream_lifespan = app.router.lifespan_context
        app.router.lifespan_context = self.lifespan

    @asynccontextmanager
    async def lifespan(self, app):
        """Upstream initializes first; its service registration cannot win afterward."""
        from laomedo.integrations.langflow.provider_connections.bindings import (
            ProviderGraphBindings,
        )

        try:
            # Upstream caches component templates during startup. Make the
            # configured service visible before that cache is populated;
            # account choices still require a verified browser request.
            ProviderGraphBindings.install(app.state.provider_connections)
            async with self._upstream_lifespan(app) as state:
                service = get_settings_service()
                self.admission.verify_settings(service)
                if self.admission.verify_database(service.auth_settings):
                    raise ProfileError("profile_setup_unavailable")
                manager = get_service_manager()
                manager.register_service_class(
                    ServiceType.AUTH_SERVICE, LocalProfileAuthService, override=True
                )
                manager.update(ServiceType.AUTH_SERVICE)
                if not isinstance(get_auth_service(), LocalProfileAuthService):
                    raise ProfileError("profile_setup_unavailable")
                controllers = app.state.provider_connections.controllers
                if controllers is not None:
                    from starlette.concurrency import run_in_threadpool

                    await run_in_threadpool(controllers.recover)
                    controllers.install()
                yield state
        finally:
            ProviderGraphBindings.release(app.state.provider_connections)
            controllers = app.state.provider_connections.controllers
            try:
                if controllers is not None:
                    from starlette.concurrency import run_in_threadpool

                    await run_in_threadpool(controllers.close)
            finally:
                app.state.provider_connections.close()
