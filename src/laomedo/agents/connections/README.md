# Agent connections

This capability owns saved Agent accounts, their admitted credential generations,
graph preferences and connection-bound runtimes. Host credentials/private_state
provide private storage and permissions; host profiles and Langflow integration
own browser authentication. Session leases here are opaque revocation identifiers.
Verified browser token renewal may carry an opaque lease forward until the renewed token expires. renew_lease preserves its original revocation identity; resolve_lease prunes expired aliases. Only the browser integration verifies cookies and supplies renewal evidence. No credentials are stored in this map.
No framework, browser-cookie, Docker SDK or ACP dependency loads on package import.

```text
connections/
  base.py          BaseProviderConnection: provider lifecycle adapter contract
  service.py       ProviderConnections: index, fencing, orchestration, preferences
  controllers.py   ProviderControllers: exact connection/generation runtime slots
  credentials.py   SavedConnectionCredential, SavedClaudeConnection: admission facades
  models.py        Shared persisted metadata and safe request/response contracts
  errors.py        ProviderConnectionError: stable ValueError boundary
  settings.py      Shared attempt and connection-count policy
../agents/
  codex/connection.py      CodexConnection: broker sign-in, staging, publication
  claude/connection.py     ClaudeConnection: official native login/profile lifecycle
  opencode/connection.py   GoConnection: explicit subscription-key custody
```

BaseProviderConnection defines provider-owned native identity verification, common attempt observation, fencing, worker
inventory, orphan ownership/reconciliation and exact revision cleanup. Providers
without asynchronous login have no pending attempts or workers. The service calls
all adapters when fencing profile/session/connection work. Orphan admission keeps
Go-marker then Claude-marker then Codex fallback order, failing closed on malformed
metadata. Provider adapters are constructed lazily through the existing AgentProviderRegistry composition root and share the service lifecycle
lock; they never create an independent admission lock.

ProviderConnections.admitted checks the exact owner, lifecycle and generation.
list projects safe summaries; begin/complete/progress/cancel dispatch to the owning
adapter. disconnect fences before cancellation; retry_cleanup removes the index
only after all adapter work and native controller cleanup are confirmed. close
fences every adapter, waits for native workers within their cleanup budget and
retains the finisher thread when workers have not settled. Graph preferences
preserve independent per-harness selections.

ProviderControllers admits requests only on the original credential generation,
inventories owned runs and reserves durable resumes before native startup.
Saved admission facades borrow or check only that exact connection; no active-account
fallback or host-login copying exists. Runtime HTTP gateways remain host-owned.

Persisted provider-connections/provider-runs/provider-leases paths, schemas, native
volume labels, callback addresses and public errors remain unchanged by this move.
The existing private SIWC helper calls are an explicit storage boundary: atomic
replacement, private-root admission, ACLs and broker refresh locks retain their
host implementations; the Agent service does not implement another store.

## Operational guarantees

Codex callback failures log only the fixed processing phase, exception type and
an allowlisted failure category (or unclassified). Credentials, callback URLs,
OAuth state, identity claims and raw exception messages are never logged. These
diagnostics distinguish exchange/verification from admission/publication without
changing the browser's safe failure or credential-preservation contract.
Pre-exchange binding refusals report only aggregate matching counts; query-shape
refusals report a fixed phase. Callback values and identity metadata stay private.
ID-token verification allows at most 30 seconds of clock drift for time claims.
Signature, issuer, audience, expiry, subject and nonce validation remain enforced;
tokens outside the bound are refused. This covers fresh tokens issued slightly
ahead of the local clock without importing or disabling provider authentication.

Provider extension: `ConnectionRecord.provider` identifies the credential owner;
graph preferences have a separate optional selector for each harness. Every saved
selector must belong to that harness and the current profile. Native login and
controller support remain separate admission gates; adding a preference field does
not enable an unavailable authentication method. Claude Code uses an official
client-owned volume; the selected OpenCode backend is OpenCode Go.

`agents/opencode/connection.py` owns `GoConnection`: `save()` admits an explicitly supplied subscription
key into an independent private profile, `summary()` reports key custody without
claiming provider identity or inference eligibility, `profile()` validates the
exact persisted key binding, and `erase()` removes only its owned credential files.
The shared controller supplies `OpenCodeAgentRuntime` with that profile. Native
tools remain disabled in the credential-bearing controller; workers are separate.

`agents/claude/connection.py` owns `ClaudeConnection`, which orchestrates the unmodified official
client's login in a dedicated labelled Docker volume. `begin()` starts a bounded
native attempt, `details()` observes its safe receipt and provider URL, `submit()`
relays the one-use code to that same native process, and `cancel()` fences it.
`profile()` admits the exact owned volume; `summary()` uses native auth status;
`erase()` requires confirmed native cleanup before removing owned credentials.
`ClaudeNativeProfile` and `ClaudeLoginAttempt` in `agents/claude/models.py` describe host-only
resource custody and process-local attempt state. The client owns all tokens and
refresh; Laomedo never reads its credential file or imports host login state.

This Agent capability owns profile-scoped provider connections, explicit login
attempts and credential admission. The initial implemented route is Codex with
app-owned Sign in with ChatGPT. OpenCode Go key custody and isolated per-connection runners are implemented. Native saved-account execution has passed for all three harnesses; multi-account and failure-recovery acceptance remain tracked in the owning PR.

`service.py` defines `ProviderConnections`: `list()` projects safe rows, `begin()`
opens one bounded loopback attempt, `complete()` verifies staged credentials and
atomically admits metadata, `cancel()` fences late completion, and `borrow()`
resolves an exact profile/connection/generation without an active-account fallback.
`controllers.py` owns `ProviderControllers`, the trusted-local host orchestration
of isolated native Codex runtimes per profile, connection and admitted generation.
It inventories running turns and native cleanup receipts, cancels only owned
runs, and confirms cleanup before removal. Pending durable resume
reservations count as active work even before the parent run record changes;
cleanup cannot complete while those observations remain unsettled. An unknown
reservation exposes Cleanup required with retry rather than an
unbounded Stopping state; credentials remain fenced and retained for recovery.
Gateway admission covers both synchronous and asynchronous resume. A closed controller
owner cannot borrow credentials or probe an account through a retained facade.
`credentials.py` defines the exact saved-connection broker facade used by those
runtimes; native controller and
model tools retain their existing separate Docker identities.
`disconnect_info()` reports affected runs and a confirmation revision;
`disconnect()` durably fences use before cancellation, and `retry_cleanup()`
reconciles an interrupted removal without reopening authentication. A failed or
unknown stop/erase remains visible and non-selectable. No provider-wide logout
is implied. Local profiles remain convenience locks in a trusted single-user
host, not isolation against arbitrary host Python or a hostile OS user.
`models.py` defines persisted metadata and safe response contracts. `settings.py`
owns fixed attempt policy; `errors.py` defines safe domain failures.

`ClaudeConnection.reconcile_orphan()` validates retained ownership metadata before
cleanup. A daemon failure or unconfirmed cleanup retains the custody receipt and
logs pending cleanup for the next startup retry, without blocking other providers.
Unreadable ownership metadata still prevents startup; cleanup never guesses owners.

Codex admission permits one saved row per verified provider email within a local
profile, in addition to rejecting repeated verified issuer/subject identities.
Claude admission identifies an account by its verified email (case-insensitive)
and organization ID together. The same email in distinct verified organizations
can have independent connections; repeating the same pair returns the existing
connection without replacing its credentials. Reconnect must retain the original
verified identity, including Claude's organization. OpenCode Go keys do not claim
a verified account identity. Existing saved rows are removed only through the
normal Disconnect workflow. Multi-organization Claude admission is covered by
fixtures; real multi-organization acceptance remains unverified.

Private state must be outside Git and tool mounts. Each profile and opaque
connection gets its own credential directory. Staging is never dispatchable.
An interrupted attempt expires; it is never replayed after restart. Login,
status, discovery and cleanup do not submit model requests. No method imports a
host login. Failed reconnects preserve the committed credential. Disconnect
requires native inventory and stop confirmation before erasing a local token.

The selected draft is specs PR #426. Implementation and live acceptance
are separate gates. Existing single-runner startup can explicitly select a broker
account. Graph-selected dispatch uses `ProviderGraphBindings`, the verified browser
principal, and an opaque selector. Operator-only source configuration is supplied
with `tools/start_local_profiles.ps1 -ProviderSourceWorkspace`; no source path is
accepted from a graph. A source checkout root containing `.git` metadata (a directory or worktree
pointer file) is not supported by split mode. Select a tracked source subtree
without its own Git metadata or runtime/cache directories; for the no-tools
showcase, `examples/skill-agent-pilot/source` is the maintained example.
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

Disconnect requests cancellation across all owned generations before reporting
unconfirmed cleanup. Pending continuation inventory uses the resume journal's
existing reconciliation: only a matching terminal attempt with verified native
and controller cleanup and no active MCP grant or runner lock can settle. An
unattested reservation remains Cleanup required; Retry never invents settlement.

Graph preferences are stored per local profile and graph UUID, outside portable
flow exports. `graph_preferences()` reads independent Codex, Claude Code and OpenCode selections;
`save_graph_preferences()` validates a connected owned row before atomically saving.
An explicit node selection overrides the graph preference. Missing or removed
accounts never fall back to another connection. Graph routes verify Flow ownership.

Retained run operations resolve the connection from the authenticated owner's
controller inventory, independently of later preference or node-selector changes.
Ambiguous or missing runs are refused; current preferences cannot redirect them.

Editor model discovery can use the same-origin graph referrer only after the
browser principal and database graph ownership are verified. Runtime graph
identity takes precedence; API calls without an owned graph context do not guess.

Claude `_create_profile()` writes exact volume ownership before daemon creation.
Per-revision locks serialize native status and cleanup without blocking logout
on the global lifecycle lock. Shutdown fences admissions immediately and retains
the custody lease until cancelled native workers settle, even after its foreground
cleanup budget ends. A committed reconnect with old-volume cleanup uncertainty
remains connected and reports that separate cleanup outcome.


## Subscription observations (#300)

`quota.py` owns `SubscriptionObservations`: `read()` returns only lease-visible
cached state; `refresh()` coalesces native reads per profile/connection/generation,
reuses fresh data and gates publication on the current lease/generation. Native
single-flight and lease visibility have separate keys. Memory-only retention and
retry/freshness bounds live in `settings.py`. Safe observation/cache contracts live
in `models.py`; canonical provider quota values live in `agents/base/models.py`.
`ProviderControllers.subscription_limits()` reserves the existing discovery fence
and releases it after exact native cleanup, preserving disconnect/cancel behavior.
`ProviderConnections.check_lease()` refuses requests from a browser lease already
revoked by logout/profile switching, including reads and account-management
writes. It does not delete saved connections. `ClaudeConnection.details()` accepts
an optional trusted-call lease; HTTP callers must pass the initiating lease before
receiving the native authorization link. Generic progress never exposes that link.

`ProviderControllers._native_failures()` names the optional Docker boundary errors
without making the SDK a base-package import requirement. `recover()` retains
failed slots on daemon outages so Settings stays available; `stop()` projects
the same failures to unconfirmed cleanup, preserving custody and Retry cleanup.

Generic progress and cancel routes pass the verified opaque browser lease to
the adapter, which matches both profile and originating lease before access.
Trusted internal callers may inspect receipts without a browser lease; the HTTP
boundary never omits it. Native identity verification stays in its provider adapter.
