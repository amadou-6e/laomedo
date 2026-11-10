"""Native Windows vault lifecycle against one fresh synthetic task-owned entry."""
from hmac import compare_digest
import secrets
from uuid import uuid4
from pydantic import SecretStr
from laomedo.host.credentials.github.vault import WindowsCredentialVault

reference = uuid4()
vault = WindowsCredentialVault()
value = SecretStr(secrets.token_urlsafe(32))
try:
    vault.store(reference, value)
    reopened = WindowsCredentialVault()
    loaded = reopened.load(reference)
    assert loaded is not None and compare_digest(loaded.get_secret_value(), value.get_secret_value())
    print("Native store and reopened-instance load verified; no other entries accessed.")
finally:
    vault.remove(reference)
    assert vault.load(reference) is None
    print("Task-owned entry removal verified.")
