"""Explicit Windows Credential Manager storage; no backend discovery or fallback."""

from hmac import compare_digest
import sys
from uuid import UUID

from pydantic import SecretStr

from laomedo.host.credentials.github.errors import GitHubVaultError


class WindowsCredentialVault:
    """Keep broker-owned secrets under independently journaled opaque references."""

    def __init__(self):
        if sys.platform != "win32":
            raise GitHubVaultError()
        try:
            from keyring.backends.Windows import WinVaultKeyring

            if WinVaultKeyring.priority <= 0:
                raise GitHubVaultError()
            self.backend = WinVaultKeyring()
            self.backend.persist = "local machine"
        except Exception:
            raise GitHubVaultError() from None

    def _target(self, reference: UUID) -> str:
        """Construct only this feature's exact target from a broker-owned UUID."""
        if not isinstance(reference, UUID):
            raise GitHubVaultError()
        return "Laomedo/GitHubConnections/" + reference.hex

    def store(self, reference: UUID, value: SecretStr) -> None:
        """Write a new reference and verify custody; never overwrite a ready value."""
        target = self._target(reference)
        try:
            secret = value.get_secret_value()
            if (
                not secret
                or self.backend.get_password(target, "credential") is not None
            ):
                raise GitHubVaultError()
            self.backend.set_password(target, "credential", secret)
            stored = self.backend.get_password(target, "credential")
            if stored is None or not compare_digest(stored.encode(), secret.encode()):
                raise GitHubVaultError()
        except Exception:
            raise GitHubVaultError() from None

    def load(self, reference: UUID) -> SecretStr | None:
        """Read an already authorized reference without exposing backend failures."""
        target = self._target(reference)
        try:
            value = self.backend.get_password(target, "credential")
            return SecretStr(value) if value is not None else None
        except Exception:
            raise GitHubVaultError() from None

    def remove(self, reference: UUID) -> None:
        """Verify absence of this reference, including an already absent entry."""
        target = self._target(reference)
        try:
            if self.backend.get_password(target, "credential") is not None:
                self.backend.delete_password(target, "credential")
            if self.backend.get_password(target, "credential") is not None:
                raise GitHubVaultError()
        except Exception:
            raise GitHubVaultError() from None
