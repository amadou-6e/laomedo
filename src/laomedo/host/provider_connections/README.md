# Saved provider connections

Provider extension: `ConnectionRecord.provider` identifies the credential owner;
graph preferences have a separate optional selector for each harness. Every saved
selector must belong to that harness and the current profile. Native login and
controller support remain separate admission gates; adding a preference field does
not enable an unavailable authentication method. Claude Code uses an official
client-owned volume; the selected OpenCode backend is OpenCode Go.

`go.py` owns `GoConnection`: `save()` admits an explicitly supplied subscription
key into an independent private profile, `summary()` reports key custody without
claiming provider identity or inference eligibility, `profile()` validates the
exact persisted key binding, and `erase()` removes only its owned credential files.
The shared controller supplies `OpenCodeAgentRuntime` with that profile. Native
tools remain disabled in the credential-bearing controller; workers are separate.

`claude.py` owns `ClaudeConnection`, which orchestrates the unmodified official
client's login in a dedicated labelled Docker volume. `begin()` starts a bounded
native attempt, `details()` observes its safe receipt and provider URL, `submit()`
relays the one-use code to that same native process, and `cancel()` fences it.
`profile()` admits the exact owned volume; `summary()` uses native auth status;
`erase()` requires confirmed native cleanup before removing owned credentials.
`ClaudeNativeProfile` and `ClaudeLoginAttempt` in `models.py` describe host-only
resource custody and process-local attempt state. The client owns all tokens and
refresh; Laomedo never reads its credential file or imports host login state.

This host capability owns profile-scoped provider connections, explicit login
attempts and credential admission. The initial implemented route is Codex with
app-owned Sign in with ChatGPT. OpenCode Go key custody and an isolated per-connection runner factory are implemented; real Go account/dispatch acceptance is pending. Claude native sign-in and isolated account binding are implemented but require real native sign-in/dispatch acceptance.

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

Admission permits one saved row per provider email within a local profile, in
addition to rejecting repeated verified issuer/subject identities. The email
comes from the validated provider identity and is compared case-insensitively
with saved provider labels, which are not user-editable. This is an additional
row-admission restriction only: it never links registrations, replaces existing
credentials, changes a connection generation or authorizes reconnect. Reconnect
continues to require the original verified issuer/subject. Existing saved rows
are removed only through the normal Disconnect workflow.

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
