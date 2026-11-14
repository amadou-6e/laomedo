"""Codex credential admission composed with the host-owned ChatGPT connection."""

from laomedo.agents.agents.base.base import BaseCredentialProvider
from laomedo.agents.agents.base.models import CredentialBinding
from laomedo.agents.agents.base.models import CredentialMaterial
from laomedo.agents.agents.base.models import CredentialRequest
from laomedo.agents.agents.base.models import CleanupObservation
from pydantic import SecretStr
from laomedo.agents.errors import RunnerError


class CodexCredentialProvider(BaseCredentialProvider):
    """Borrow selected credentials without owning OAuth refresh or host login files."""

    def __init__(self, agent):
        """Bind the host-admitted Agent connection; perform no credential lookup."""
        self.agent = agent

    def borrow(self) -> CredentialMaterial:
        """Obtain exactly one native access-token observation without retaining its secret."""
        if self.agent.auth is None:
            return CredentialMaterial(
                binding=CredentialBinding(
                    credential_mode="dedicated_volume",
                    credential_ref=None,
                    auth_outcome="unverified",
                )
            )
        token, identity = self.agent.auth.access_token()
        return CredentialMaterial(
            token=SecretStr(token),
            identity=identity,
            binding=CredentialBinding(
                credential_mode="chatgpt_plan_oauth",
                credential_ref=identity.get("credential_ref"),
                auth_outcome=identity.get("auth_outcome", "unverified"),
            ),
        )

    def prepare(self, request: CredentialRequest) -> CredentialBinding:
        """Delegate selected-connection refresh to its existing host owner."""
        if request.minimum_validity_seconds is not None or request.deadline is not None:
            raise RunnerError("credential_constraints_unsupported")
        return self.borrow().binding

    def validate(self, request: CredentialRequest) -> CredentialBinding:
        """Recheck the admitted host connection; do not certify a borrowed volume login."""
        if request.minimum_validity_seconds is not None or request.deadline is not None:
            raise RunnerError("credential_constraints_unsupported")
        return self.borrow().binding

    def release(self) -> CleanupObservation:
        """No secret is retained here and borrowed host credentials are not revoked."""
        return CleanupObservation(confirmed=True, scope="codex_credential_borrow_only")
