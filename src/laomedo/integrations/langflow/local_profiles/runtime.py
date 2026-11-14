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
from laomedo.integrations.langflow.local_profiles.errors import ProfileError
from laomedo.integrations.langflow.local_profiles.registry import LocalProfileRegistry
from laomedo.integrations.langflow.local_profiles.routes import router


class LocalProfileRuntime:
    """Admit before migration and verify the final service before accepting traffic."""

    def __init__(self, runtime_root):
        self.admission = ProfileRuntimeAdmission(runtime_root)
        self._upstream_lifespan = None

    def configure(self, app):
        """Install profile-only routes before the caller mounts the SPA fallback."""
        self.admission.prepare(get_settings_service())
        app.state.local_profiles_enabled = True
        app.state.local_profile_registry = LocalProfileRegistry()
        app.include_router(router)
        app.add_middleware(LocalProfileBoundary, port=self.admission.marker.port)
        self._upstream_lifespan = app.router.lifespan_context
        app.router.lifespan_context = self.lifespan

    @asynccontextmanager
    async def lifespan(self, app):
        """Upstream initializes first; its service registration cannot win afterward."""
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
            yield state
