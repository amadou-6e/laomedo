"""Trusted credential process application, without native graph execution APIs."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from langflow.api.v1.login import router as login_router
from langflow.api.v1.users import read_current_user
from langflow.services.database.models.user.model import UserRead
from langflow.services.rate_limit import get_rate_limiter
from langflow.services.utils import initialize_services, teardown_services
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from laomedo.integrations.langflow.authentication.runtime import PrivateBrowserRuntime
from laomedo.integrations.langflow.authentication.settings import PrivateBrowserSettings
from laomedo.integrations.langflow.local_profiles.routes import profile_mode
from laomedo.integrations.langflow.local_profiles.runtime import LocalProfileRuntime


class PrivateBrokerRuntime:
    """Compose trusted identity and custody without creating a Langflow graph app."""

    def __init__(
        self,
        profile_runtime: LocalProfileRuntime,
        settings: PrivateBrowserSettings,
    ):
        """Use admitted explicit runtime objects, never ambient account credentials."""
        self.profile_runtime = profile_runtime
        self.private_runtime = PrivateBrowserRuntime(settings)

    def create_app(self):
        """Expose identity/private controls only; unknown native APIs remain absent.

        In particular, importing native login handlers does not install the
        main application's graph builders, component editors or MCP lifecycle.
        Profile and private runtime configuration occurs before serving traffic.
        """
        app = FastAPI(
            title="Laomedo credential broker",
            docs_url=None,
            redoc_url=None,
            openapi_url=None,
            lifespan=self.lifespan,
        )
        app.state.limiter = get_rate_limiter()
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.include_router(login_router, prefix="/api/v1")
        app.add_api_route(
            "/api/v1/users/whoami",
            read_current_user,
            methods=["GET"],
            response_model=UserRead,
        )
        app.add_api_route("/api/v1/laomedo/profile-mode", profile_mode, methods=["GET"])
        self.profile_runtime.configure(app)
        self.private_runtime.configure(app)
        return app

    @asynccontextmanager
    async def lifespan(self, app):
        """Initialize trusted database/auth services without graph startup tasks."""
        await initialize_services()
        try:
            yield
        finally:
            await teardown_services()
