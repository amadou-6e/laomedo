# GitHub credential custody on native Windows

`vault.py` owns `WindowsCredentialVault`; `errors.py` owns `GitHubVaultError`.
Only the private connection broker may supply vault references, after resolving
their profile/connection ownership. No route accepts a vault key from a browser.

- Construction selects `WinVaultKeyring` directly, with local-machine persistence.
  It does not discover backends, import ambient credentials or change keyring's
  global configuration. Unsupported systems or unavailable Windows APIs fail.
- `store` writes a new opaque UUID reference and verifies read-back. A failed
  operation may have written that reference: the broker must journal provisional
  references before storage and retain them for cleanup. It must not overwrite a
  ready credential; rotation stores a new reference before committing metadata.
- `load` returns a masked `SecretStr` or no value. Its caller must authorize the
  connection before lookup; possession of a reference is not read authority.
- `remove` verifies absence, including an already absent value. A failure never
  claims deletion or GitHub-side token revocation.

Each reference has a distinct service target, avoiding the backend's multi-user
collision/relocation behavior. Credentials remain available across app restarts,
but are not configured to roam with an enterprise profile. This is OS-user
custody, not isolation from malicious processes running as the same Windows user.
The connection broker must serialize lifecycle operations; this adapter does not
claim a cross-process compare-and-swap operation.

Tests use internal backend controls. Separately run the native lifecycle against
only a fresh task-owned reference, without reading or enumerating other entries.
