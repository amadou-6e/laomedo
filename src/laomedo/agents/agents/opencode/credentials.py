"""OpenCode-native validity policy over the explicitly admitted private profile."""

from laomedo.agents.agents.base.interim import BaseCredentialProvider
from laomedo.agents.agents.base.models.credentials import (
    CredentialBinding,
    CredentialRequest,
)
from laomedo.agents.agents.base.models.runtime import CleanupObservation
from laomedo.agents.agents.opencode.utils import check_auth_fresh
from laomedo.agents.errors import RunnerError


class OpenCodeCredentialProvider(BaseCredentialProvider):
    """Validate a borrowed provider profile without refreshing or copying its secret."""

    def __init__(self, profile):
        """Bind an already private/admitted profile without opening credential files."""
        self.profile = profile

    def prepare(self, request: CredentialRequest) -> CredentialBinding:
        """Admit the native validity record before any profile mount or model turn."""
        return self.validate(request)

    def validate(self, request: CredentialRequest) -> CredentialBinding:
        """Keep native key/token expiry and fingerprint checks in the provider owner."""
        if request.deadline is not None:
            raise RunnerError("credential_constraints_unsupported")
        options = (
            {"minimum_validity_seconds": request.minimum_validity_seconds}
            if request.minimum_validity_seconds is not None
            else {}
        )
        check_auth_fresh(self.profile, **options)
        return CredentialBinding(
            credential_mode="private_profile",
            credential_ref=None,
            auth_outcome="validity_checked",
        )

    def release(self) -> CleanupObservation:
        """Release the borrow; profile deletion/refresh is never owned by this service."""
        return CleanupObservation(
            confirmed=True, scope="opencode_credential_borrow_only"
        )
