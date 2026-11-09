"""Claude-native login mirroring and zero-turn authentication admission."""

import hashlib
import json
import time
from laomedo.agents.agents.base.interim import BaseCredentialProvider
from laomedo.agents.agents.base.models.credentials import (
    CredentialBinding,
    CredentialRequest,
)
from laomedo.agents.agents.base.models.runtime import CleanupObservation
from laomedo.agents.agents.claude.auth.settings import Settings
from laomedo.agents.agents.claude.auth.errors import LocalClaudeLoginError
from laomedo.agents.agents.claude.auth.utils import mirror_login
from laomedo.agents.errors import RunnerError


class ClaudeCredentialProvider(BaseCredentialProvider):
    """Own Claude admission; borrowed host login refresh remains native and opt-in."""

    def __init__(self, agent):
        """Bind native control/mirror policy without performing login or model work."""
        self.agent = agent

    def prepare(self, request: CredentialRequest) -> CredentialBinding:
        """Mirror access-only state when opted in, preserving original validity limits."""
        minimum_validity_seconds, deadline = (
            request.minimum_validity_seconds,
            request.deadline,
        )
        if Settings().mirror_host_login == "1":
            try:
                options = {"deadline": deadline} if deadline is not None else {}
                mirror_login(
                    self.agent.container.profile,
                    self.agent.container.image_id,
                    minimum_validity_seconds=minimum_validity_seconds
                    or self.agent.turn_timeout,
                    **options,
                )
            except LocalClaudeLoginError as error:
                if str(error) == "claude_host_login_unavailable":
                    raise RunnerError("claude_host_login_unavailable") from None
                if str(error) == "claude_host_login_expired":
                    raise RunnerError("claude_host_login_expired") from None
                raise RunnerError("claude_local_login_copy_failed") from None

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
        self.agent._mirror_host_login(
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
