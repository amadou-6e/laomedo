# Saved provider connections

This host capability owns profile-scoped provider connections, explicit login
attempts and credential admission. The initial implemented route is Codex with
app-owned Sign in with ChatGPT. Claude, OpenCode and API-key routes are unavailable.

`service.py` defines `ProviderConnections`: `list()` projects safe rows, `begin()`
opens one bounded loopback attempt, `complete()` verifies staged credentials and
atomically admits metadata, `cancel()` fences late completion, and `borrow()`
resolves an exact profile/connection/generation without an active-account fallback.
`controllers.py` owns `ProviderControllers`, the trusted-local host orchestration
of isolated native Codex runtimes per profile, connection and admitted generation.
It inventories running turns and native cleanup receipts, cancels only owned
runs, and confirms cleanup before removal. `credentials.py` defines the exact
saved-connection broker facade used by those runtimes; native controller and
model tools retain their existing separate Docker identities.
`disconnect_info()` reports affected runs and a confirmation revision;
`disconnect()` durably fences use before cancellation, and `retry_cleanup()`
reconciles an interrupted removal without reopening authentication. A failed or
unknown stop/erase remains visible and non-selectable. No provider-wide logout
is implied. Local profiles remain convenience locks in a trusted single-user
host, not isolation against arbitrary host Python or a hostile OS user.
`models.py` defines persisted metadata and safe response contracts. `settings.py`
owns fixed attempt policy; `errors.py` defines safe domain failures.

Private state must be outside Git and tool mounts. Each profile and opaque
connection gets its own credential directory. Staging is never dispatchable.
An interrupted attempt expires; it is never replayed after restart. Login,
status, discovery and cleanup do not submit model requests. No method imports a
host login. Failed reconnects preserve the committed credential. Disconnect
requires native inventory and stop confirmation before erasing a local token.

The selected draft is specs PR #426 at eb18f67. Implementation and live acceptance
are separate gates. Existing single-runner startup can explicitly select a broker
account. Graph-selected dispatch uses `ProviderGraphBindings`, the verified browser
principal, and an opaque selector. Operator-only source configuration is supplied
with `tools/start_local_profiles.ps1 -ProviderSourceWorkspace`; no source path is
accepted from a graph. A source checkout root containing a `.git` directory is
not supported by split mode; use a clean Git worktree or a tracked subtree.
`-LangflowSourceRoot` optionally selects the matching pinned, overlaid backend/LFX
for native development previews; dependencies must match that checkout. Frontend
and backend overlays must both be installed for portable export/import policy.

The runtime holds an exclusive store lease until `close()`. Startup scrubs only
canonical unindexed vaults and crash-left staging; unreadable admission metadata
blocks cleanup rather than guessing ownership. Failed publication is reconciled
by reading the atomic index before reporting its result. Routine token rotation
advances the broker `credential_generation`; the saved row's `generation` is the
stable `connection_generation`. Borrowed metadata exposes both explicitly. Old
local token files are scrubbed after reconnect; remote grant revocation is not
claimed. Native saved-account dispatch, concurrent cancellation, two-account
isolation and restart cleanup still need live acceptance; synthetic tests alone
do not establish those outcomes.
