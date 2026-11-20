"""Exact saved-connection credential facade for the isolated native controller."""

from laomedo.host.credentials.siwc.connection import ChatGPTConnection
from laomedo.host.credentials.siwc.errors import AuthError
from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.agents.claude.models import ClaudeAccountIdentity
from laomedo.agents.errors import RunnerError


class SavedConnectionCredential:
    """Keep every borrow and authorization probe behind the durable admission fence."""

    def __init__(self, service, profile_id, connection_id, generation):
        """Bind trusted host identity; never retain or import a token."""
        self.service = service
        self.profile_id = profile_id
        self.connection_id = connection_id
        self.generation = generation
        with service._lock:
            self.client_id = service._record(profile_id, connection_id).client_id

    def access_token(self, client_id):
        """Borrow this epoch only, mapping refusal to the existing auth boundary."""
        if client_id != self.client_id:
            raise AuthError("auth_account_mismatch")
        try:
            with self.service._lock:
                if (
                    self.service.controllers is not None
                    and self.service.controllers.closed
                ):
                    raise AuthError("auth_revoked")
                return self.service.borrow(
                    self.profile_id, self.connection_id, self.generation
                )
        except ProviderConnectionError:
            raise AuthError("auth_revoked") from None

    def account(self, client_id):
        """Read an admitted account without refreshing; disconnect invalidates it immediately."""
        if client_id != self.client_id:
            raise AuthError("auth_account_mismatch")
        try:
            with self.service._lock:
                if (
                    self.service.controllers is not None
                    and self.service.controllers.closed
                ):
                    raise AuthError("auth_revoked")
                record = self.service.admitted(
                    self.profile_id, self.connection_id, self.generation
                )
                account = self.service.codex._broker(
                    self.profile_id, record.credential_id
                ).account(client_id)
                return {**account, "connection_generation": record.generation}
        except ProviderConnectionError:
            raise AuthError("auth_revoked") from None

    def summary(self, account):
        """Preserve native observations and add the stable admission epoch for probes."""
        return {
            **ChatGPTConnection.summary(account),
            "connection_generation": account["connection_generation"],
        }


class SavedClaudeConnection:
    """Fence the official client's own profile without importing or reading tokens."""

    def __init__(self, service, profile_id, connection_id, generation):
        """Bind exact host-owned account identity and stable generation."""
        self.service = service
        self.profile_id = profile_id
        self.connection_id = connection_id
        self.generation = generation

    def check(self):
        """Require an admitted unchanged account and its exact native profile."""
        try:
            with self.service._lock:
                if self.service.controllers is None or self.service.controllers.closed:
                    raise ProviderConnectionError("provider_connection_unavailable")
                record = self.service.admitted(
                    self.profile_id, self.connection_id, self.generation
                )
            descriptor = self.service.claude.profile(self.profile_id, record)
            with self.service._lock:
                self.service.admitted(
                    self.profile_id, self.connection_id, self.generation
                )
            return descriptor
        except ProviderConnectionError as error:
            raise RunnerError(error.code) from None
        except Exception:
            raise RunnerError("provider_connection_unavailable") from None

    def validate(self, auth):
        """Match native account/workspace to the saved generation before admission."""
        self.check()
        try:
            identity = ClaudeAccountIdentity(
                email=auth.get("email"), organization_id=auth.get("orgId")
            )
            with self.service._lock:
                record = self.service.admitted(
                    self.profile_id, self.connection_id, self.generation
                )
                if identity.subject_hash() != record.subject_hash:
                    raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise RunnerError("provider_connection_changed") from None
