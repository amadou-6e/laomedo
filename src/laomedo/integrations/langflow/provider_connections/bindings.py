"""Trusted graph-user routing for the opt-in single-worker local profile app."""

from uuid import UUID
from contextvars import ContextVar
from urllib.parse import urlsplit

from laomedo.agents.connections.controllers import ProviderControllers
from laomedo.agents.connections.errors import ProviderConnectionError


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
            if row.lifecycle == "connected" and row.provider == component.provider_id
        ]

    @classmethod
    def stage_review(cls, component, source_run, body):
        """Bind a graph review to its authenticated owner, target and exact request."""
        owner = cls.owner(component)
        session = cls.session.get()
        endpoint = getattr(component, "_saved_endpoint", None)
        if session is None or not endpoint or session.profile_id != owner:
            raise ProviderConnectionError("verified_review_unavailable")
        port = urlsplit(endpoint[0]).port
        manager = ProviderControllers.current()
        with cls.service._lock:
            matches = [
                slot
                for slot in manager.slots.values()
                if slot.profile_id == owner
                and slot.scope == "graph"
                and slot.server is not None
                and slot.server.server_address[1] == port
            ]
            if len(matches) != 1:
                raise ProviderConnectionError("verified_review_unavailable")
            target = matches[0]
        return manager.stage_review_request(
            owner, session.lease_hash, source_run, target, body
        )

    @classmethod
    def endpoint(cls, component, selected, *, run_id=None):
        """Resolve one exact compatible connection without cross-harness fallback."""
        if component.provider_id not in {"codex", "claude", "opencode"}:
            raise ProviderConnectionError("provider_method_unavailable")
        if run_id:
            selected = ProviderControllers.current().connection_for_run(
                cls.owner(component), run_id
            )
        if not selected:
            flow_id = getattr(getattr(component, "graph", None), "flow_id", None)
            if flow_id is None:
                session = cls.session.get()
                flow_id = session.flow_id if session is not None else None
            try:
                flow_id = UUID(str(flow_id))
            except (ValueError, TypeError):
                raise ProviderConnectionError("provider_connection_required") from None
            selected = cls.service.graph_preferences(cls.owner(component), flow_id)
            selected = getattr(selected, component.provider_id)
        try:
            connection_id = UUID(str(selected))
        except (ValueError, TypeError, AttributeError):
            raise ProviderConnectionError("provider_connection_required") from None
        record = cls.service._record(cls.owner(component), connection_id)
        if record.provider != component.provider_id:
            raise ProviderConnectionError("provider_connection_unavailable")
        return ProviderControllers.current().endpoint(
            cls.owner(component), connection_id, run_id=run_id
        )
