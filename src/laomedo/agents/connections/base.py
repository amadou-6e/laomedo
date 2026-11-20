"""Common lifecycle observation and fencing for saved Agent connections."""

from abc import ABC, abstractmethod

from laomedo.agents.connections.errors import ProviderConnectionError


class BaseProviderConnection(ABC):
    """Adapt provider custody without hiding native work from shared admission."""

    cleanup_seconds = 0
    summary_outside_lock = False

    def has_attempt(self, attempt_id):
        """Report whether this adapter owns the opaque pending attempt."""
        return False

    def login_in_progress(self, profile_id):
        """Report login work that prevents another sign-in for this profile."""
        return False

    def unsettled(self, profile_id, connection_id):
        """Report native work that must settle before revision cleanup."""
        return False

    def workers(self):
        """Return live owned login workers; key-only providers have none."""
        return []

    def fence_all(self):
        """Fence every pending attempt; key-only providers have none."""
        return None

    def cancel_profile(self, profile_id):
        """Fence a profile's login attempts; key-only providers have none."""
        return None

    def cancel_lease(self, lease_hash):
        """Fence attempts using the opaque lease; no browser types cross here."""
        return None

    def fence_connection(self, profile_id, connection_id):
        """Fence pending work for the exact connection before cleanup."""
        return None

    def borrow(self, profile_id, connection_id, generation):
        """Refuse token borrowing when this native provider does not expose tokens."""
        raise ProviderConnectionError("provider_method_unavailable")

    @abstractmethod
    def owns(self, vault):
        """Identify provider custody before the unmarked Codex fallback."""
        raise NotImplementedError

    @abstractmethod
    def summary(self, profile_id, record):
        """Project safe account observations without starting inference."""
        raise NotImplementedError

    @abstractmethod
    def reconcile_orphan(self, vault, active=False):
        """Recover only exact owned orphan state, preserving admitted custody."""
        raise NotImplementedError

    @abstractmethod
    def erase_revision(self, profile_id, record):
        """Remove only settled, fenced credentials for this exact connection."""
        raise NotImplementedError

    def validate_identity(self, record, auth):
        """Refuse native identity validation unless the adapter owns that protocol."""
        raise ProviderConnectionError("provider_connection_changed")

    def check_attempt(self, profile_id, attempt_id, lease_hash):
        """Reject attempt access unless a login-capable adapter verifies ownership."""
        raise ProviderConnectionError("provider_login_expired")
