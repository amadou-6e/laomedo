"""Trusted graph-user routing for the opt-in single-worker local profile app."""

from uuid import UUID
from contextvars import ContextVar

from laomedo.host.provider_connections.controllers import ProviderControllers
from laomedo.host.provider_connections.errors import ProviderConnectionError


class ProviderGraphBindings:
    """Resolve opaque local selectors; never accept host paths or profile inputs."""

    service = None
    session = ContextVar("laomedo_provider_browser_session", default=None)

    @classmethod
    def install(cls, service):
        """Bind the explicitly admitted profile app before it accepts requests."""
        if cls.service is not None:
            raise ProviderConnectionError("provider_runner_unavailable")
        cls.service = service

    @classmethod
    def release(cls, service):
        """Clear only the app that owns this worker's binding context."""
        if cls.service is service:
            cls.service = None

    @classmethod
    def owner(cls, component):
        """Read the executing identity injected by Langflow, never a graph input."""
        from langflow.services.auth.context import (
            AUTH_METHOD_JWT,
            get_current_auth_context,
        )

        authentication = get_current_auth_context()
        session = cls.session.get()
        if (
            authentication is None
            or authentication.method != AUTH_METHOD_JWT
            or session is None
            or session.lease_hash in cls.service.revoked_leases
        ):
            raise ProviderConnectionError("provider_session_required")
        try:
            owner = UUID(str(component.user_id))
        except (AttributeError, ValueError, TypeError):
            raise ProviderConnectionError("provider_connection_unavailable") from None
        if owner != session.profile_id:
            raise ProviderConnectionError("provider_session_required")
        return owner

    @classmethod
    def choices(cls, component):
        """Observe only the execution profile's safe rows, with no native startup."""
        return [
            row
            for row in cls.service.list(cls.owner(component))
            if row.lifecycle == "connected"
        ]

    @classmethod
    def endpoint(cls, component, selected, *, run_id=None):
        """Resolve one explicit profile-owned Codex connection without fallback."""
        if component.provider_id != "codex":
            raise ProviderConnectionError("provider_method_unavailable")
        if not selected:
            flow_id = getattr(getattr(component, "graph", None), "flow_id", None)
            try:
                flow_id = UUID(str(flow_id))
            except (ValueError, TypeError):
                raise ProviderConnectionError("provider_connection_required") from None
            selected = cls.service.graph_preferences(
                cls.owner(component), flow_id
            ).codex
        try:
            connection_id = UUID(str(selected))
        except (ValueError, TypeError, AttributeError):
            raise ProviderConnectionError("provider_connection_required") from None
        return ProviderControllers.current().endpoint(
            cls.owner(component), connection_id, run_id=run_id
        )
