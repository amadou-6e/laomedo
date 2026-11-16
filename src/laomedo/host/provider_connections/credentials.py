"""Exact saved-connection credential facade for the isolated native controller."""

from laomedo.host.credentials.siwc.connection import ChatGPTConnection
from laomedo.host.credentials.siwc.errors import AuthError
from laomedo.host.provider_connections.errors import ProviderConnectionError


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
                record = self.service.admitted(
                    self.profile_id, self.connection_id, self.generation
                )
                account = self.service._broker(
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
