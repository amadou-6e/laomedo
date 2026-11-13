"""Internal custody controls; a fake backend is not native vault acceptance."""

from importlib.util import find_spec
import unittest
from unittest.mock import patch
from uuid import uuid4

from pydantic import SecretStr

from laomedo.host.credentials.github.errors import GitHubVaultError
from laomedo.host.credentials.github.vault import WindowsCredentialVault


class NativeVaultControl:
    priority = 5

    def __init__(self):
        self.values = {}
        self.failure = False
        self.ignore_delete = False

    def get_password(self, target, username):
        if self.failure:
            raise RuntimeError("synthetic provider diagnostic")
        return self.values.get((target, username))

    def set_password(self, target, username, password):
        self.values[target, username] = password

    def delete_password(self, target, username):
        if not self.ignore_delete:
            self.values.pop((target, username), None)


class WindowsCredentialVaultTests(unittest.TestCase):
    def setUp(self):
        self.vault = object.__new__(WindowsCredentialVault)
        self.backend = NativeVaultControl()
        self.vault.backend = self.backend
        self.reference = uuid4()

    def test_scoped_store_load_and_idempotent_verified_removal(self):
        value = SecretStr("synthetic-not-a-provider-token")
        self.assertIsNone(self.vault.load(self.reference))
        self.vault.store(self.reference, value)
        self.assertEqual(self.vault.load(self.reference), value)
        self.assertEqual(
            list(self.backend.values),
            [("Laomedo/GitHubConnections/" + self.reference.hex, "credential")],
        )
        self.vault.remove(self.reference)
        self.vault.remove(self.reference)
        self.assertIsNone(self.vault.load(self.reference))

    def test_new_reference_does_not_relocate_or_overwrite_another(self):
        first = SecretStr("synthetic-first")
        self.vault.store(self.reference, first)
        with self.assertRaises(GitHubVaultError):
            self.vault.store(self.reference, SecretStr("synthetic-replacement"))
        second = uuid4()
        self.vault.store(second, SecretStr("synthetic-second"))
        self.assertEqual(self.vault.load(self.reference), first)
        self.vault.remove(second)
        self.assertEqual(self.vault.load(self.reference), first)

    def test_backend_failure_exposes_only_stable_code(self):
        self.backend.failure = True
        with self.assertRaises(GitHubVaultError) as caught:
            self.vault.load(self.reference)
        self.assertEqual(caught.exception.args, ("github_credential_unavailable",))
        self.assertIsNone(caught.exception.__cause__)

    def test_unconfirmed_deletion_is_not_reported_as_removed(self):
        self.vault.store(self.reference, SecretStr("synthetic-value"))
        self.backend.ignore_delete = True
        with self.assertRaises(GitHubVaultError):
            self.vault.remove(self.reference)
        self.assertIsNotNone(self.vault.load(self.reference))

    def test_arbitrary_target_and_empty_credential_are_refused(self):
        with self.assertRaises(GitHubVaultError):
            self.vault.load("another-app-target")
        with self.assertRaises(GitHubVaultError):
            self.vault.store(self.reference, SecretStr(""))
        self.assertFalse(self.backend.values)

    def test_unsupported_platform_cannot_select_fallback(self):
        with patch("laomedo.host.credentials.github.vault.sys.platform", "linux"):
            with self.assertRaises(GitHubVaultError):
                WindowsCredentialVault()

    @unittest.skipUnless(find_spec("keyring"), "Optional Windows keyring dependency")
    def test_constructor_selects_windows_backend_with_local_persistence(self):
        with patch("laomedo.host.credentials.github.vault.sys.platform", "win32"):
            with patch("keyring.backends.Windows.WinVaultKeyring", NativeVaultControl):
                vault = WindowsCredentialVault()
        self.assertIsInstance(vault.backend, NativeVaultControl)
        self.assertEqual(vault.backend.persist, "local machine")
