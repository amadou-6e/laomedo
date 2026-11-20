"""Claude-native profile and zero-turn authentication admission."""

import hashlib
import json
import time
from laomedo.agents.agents.base.base import BaseCredentialProvider
from laomedo.agents.agents.base.models import CredentialBinding
from laomedo.agents.agents.base.models import CredentialRequest
from laomedo.agents.agents.base.models import CleanupObservation
from laomedo.agents.errors import RunnerError


class ClaudeCredentialProvider(BaseCredentialProvider):
    """Own admission to the explicitly authenticated native profile."""

    def __init__(self, agent):
        """Bind native control policy without performing login or model work."""
        self.agent = agent

    def prepare(self, request: CredentialRequest) -> CredentialBinding:
        """Check saved-connection admission without reading host login files."""
        saved = getattr(self.agent, "auth_connection", None)
        if saved is not None:
            saved.check()
        return CredentialBinding(
            credential_mode="dedicated_volume",
            credential_ref=None,
            auth_outcome="prepared",
        )

    def validate(self, request: CredentialRequest) -> CredentialBinding:
        """Observe native subscription admission and return only hashed public identity."""
        minimum_validity_seconds, deadline = (
            request.minimum_validity_seconds,
            request.deadline,
        )
        timeout = request.timeout_seconds
        self.agent._prepare_credentials(
            minimum_validity_seconds=minimum_validity_seconds, deadline=deadline
        )
        options = {}
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RunnerError("claude_turn_timeout")
            timeout = min(timeout, remaining)
            options["deadline"] = deadline
        checked = self.agent.container.control(
            ["auth", "status"], timeout=timeout, **options
        )
        try:
            auth = json.loads(checked.stdout)
        except ValueError:
            raise RunnerError("claude_subscription_unavailable") from None
        if (
            checked.exit_code
            or not auth.get("loggedIn")
            or auth.get("authMethod") != "claude.ai"
        ):
            raise RunnerError("claude_subscription_unavailable")
        saved = getattr(self.agent, "auth_connection", None)
        if saved is not None:
            saved.validate(auth)
        identity = {key: auth[key] for key in ("email", "orgId") if auth.get(key)}
        reference = (
            "sha256:"
            + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            if identity
            else None
        )

        return CredentialBinding(
            credential_mode="dedicated_volume",
            credential_ref=reference,
            auth_outcome="authenticated",
        )

    def release(self) -> CleanupObservation:
        """Mirror helpers own their temporary cleanup; never delete a borrowed volume."""
        return CleanupObservation(confirmed=True, scope="claude_credential_borrow_only")
