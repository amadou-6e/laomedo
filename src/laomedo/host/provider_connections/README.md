# Saved provider connections

This host capability owns profile-scoped provider connections, explicit login
attempts and credential admission. The initial implemented route is Codex with
app-owned Sign in with ChatGPT. Claude, OpenCode and API-key routes are unavailable.

`service.py` defines `ProviderConnections`: `list()` projects safe rows, `begin()`
opens one bounded loopback attempt, `complete()` verifies staged credentials and
atomically admits metadata, `cancel()` fences late completion, and `borrow()`
resolves an exact profile/connection/generation without an active-account fallback.
`models.py` defines persisted metadata and safe response contracts. `settings.py`
owns fixed attempt policy; `errors.py` defines safe domain failures.

Private state must be outside Git and tool mounts. Each profile and opaque
connection gets its own credential directory. Staging is never dispatchable.
An interrupted attempt expires; it is never replayed after restart. No method
imports a host login or submits a model request. Failed reconnects preserve the
committed credential. Disconnect admission remains unavailable until the runner
can report and fence every controller using that connection; local token deletion
alone is not presented as successful disconnection.

The selected draft is specs PR #426 at 94e81ad4. Implementation and live acceptance
are separate gates. Existing single-runner startup can explicitly select a broker
account, but graph-selected per-profile runtime dispatch is still being integrated.
