# Application assistant

## Complete flow authoring (issue311)

`ComponentCatalog` owns metadata-only discovery, schema revisions and compilation;
`WorkflowConfiguration` in `configuration.py` resolves audited configuration and
readiness without executing component hooks. Request/result and resolution records
remain in `models.py`; fixed bounds and supported families belong to `settings.py`.
`WorkflowRunEvidence` in `evidence.py` projects and retains bounded actual outputs
under existing assistant database ownership, then releases them only for the exact
authorized conversation/action. `WorkflowActions` remains approval/execution owner;
the private MCP dispatcher composes these services. Existing graph persistence and
provider/Skill/MCP owners remain authoritative. Discovery and validation never
submit a model task. Real acceptance and independent review are pending.

Graph inspection exposes node positions. An approved edit can move identified
nodes to explicit bounded canvas coordinates while preserving all other graph
data; moves participate in the same revision and approval checks as other edits.

Audited adapters are exact-source Codex, Claude, OpenCode, Skill and MCPTools
components. Other installed components expose static typed fields and compatible
ports; unsupported dynamic fields remain explicit. Adapter classification uses the
installed template's canonical name, preserving its namespaced registry identity
in saved graphs; exact reviewed source digests remain mandatory. Agent model depends on the
explicit saved account, and effort depends on its selected model. Skill revisions
are pinned within the existing host-level imported registry (the same registry
already listed by `list_skills`); this feature introduces no private Skill owner.
Combining source graphs reconstructs a new candidate through the same resolver;
it never copies resource authority or unmentioned private selectors. Existing-node
patches preserve unmentioned bytes, and changed resource fields need a fresh
resolution. Resolved selectors are made visible in the editor for inspection.
Resolved dropdowns retain only their verified selected choice as presentation
metadata, so opening a draft does not refresh empty choices and clear dependent
selections. This is not a live capability catalogue; explicit refresh and runtime
admission remain authoritative. New drafts omit cached dynamic choices, and
unresolved audited string selectors use an empty string for the native editor.

The exact-source GitHub Issue adapter resolves repository and issue selectors
only through a host service that enforces anonymous public reads. Its internal
public-only pin is preserved at execution. Credentialed or private issue services
cannot satisfy that resolution; saved-account access remains separately scoped.

The digest-pinned MCPTools adapter uses the installed `component_as_tool` /
`to_toolkit` Toolset contract. It saves `tool_mode=True` and removes the single-tool
selection requirement; discovery does not invoke its refresh hook. Its name-only
selector is resolved at execution by the installed component's owner-scoped
`get_server` lookup; embedded configuration and headers are never accepted.
Portable exports clear machine-local MCP selectors as well as provider accounts.

The owner permits assistant-requested cancellation of previously approved runs
in the same conversation, without a second approval. `GraphExecution` couples
the exact local task with its entry fence: cancellation before dispatch records
`not_dispatched`; cancellation before the coroutine's first instruction is settled
by the runtime callback. After dispatch, only execution-owner observations settle
the outcome. Shutdown waits for task settlement callbacks before releasing owners.

`GraphBrowserAuthority` retains only the verified JWT authentication metadata and
provider browser-session metadata for one active `AuthoringContext`. Automatic
run admission uses a fresh context containing those two values; it never inherits
the private MCP request or chat runner's other context variables. Missing,
mismatched or revoked captures refuse before admission. Human approvals retain
normal request inheritance. Captures are removed on turn release, session
revocation and shutdown. An admitted graph remains independent of chat Stop, while
dispatch still checks the current app session and native endpoints recheck leases.

Explicit human-entered Claude `/usage`, without arguments and advertised as
non-model work, uses the existing atomic decision/dispatch path immediately.
Assistant-proposed usage still requires human approval; other commands retain
their current policy, including Codex's existing direct status behavior.

## Browser session identity

`AssistantSession` is the durable browser authority and revocation fence.
`AssistantSessionAlias` binds a verified renewed access-token fingerprint to that
same authority; it stores no token. `AssistantStore.admit_session()` returns the
canonical key and only accepts a new binding from the normal profile boundary's
verified renewal. `canonical_session_key()` resolves that identity for active
work; `revoke()` atomically retains even an unseen renewal binding and revokes its
root before sign-out completes. Runtime admission remembers verified canonical
keys for active work; logout synchronously fences known keys and removes tool
contexts before any database await. Cleanup runs even if persistence fails or
the logout lookup times out. Owner mismatches, conflicting bindings and revoked roots
refuse. Restart cannot turn a known renewed token into a new approval identity.
Unrelated logins and pre-fix proposals are not rebound.
An unobserved renewal lost with the provider's in-memory map during restart
cannot inherit the original approval identity. That path fails closed and cannot
identify the earlier root for logout; known persisted aliases remain fenced.

## Resume recovery (#303)

Terminal OpenCode records confirm all controller and worker resource cleanup
through `controller_cleanup="confirmed"`. Reconciliation consumes that provider
guarantee, not Codex/Claude's separate single-controller `container_ownership`
receipt. Unverified OpenCode cleanup still fences sending; observing a terminal
record never replays its prompt.

`AssistantRuntime.reconcile()` observes a resumed message using the conversation's
existing run and the reserved attempt identity, even if the POST acknowledgement
was lost. It never resubmits the operation. An unavailable lookup keeps the outcome
unconfirmed. Activity reads use the runner's supported maximum of 200 records.
The shared ACP client preserves an explicit authentication-required category;
provider sign-in failures must not be described as uncertain remote execution.

Persistence, declarative metadata validation, atomic workflow receipts, MCP
hosting, direct provider orchestration and chat rendering form one application
feature. Controlled tests and real provider/editor acceptance are separate gates.

`AssistantStore.upgrade_retained()` prepares only assistant-owned tables when an
upstream user table already exists, before Langflow checks shared ORM metadata.
It does not initialize or alter upstream authentication tables. Fresh upstream
database initialization remains upstream-owned; ordinary `initialize()` completes
feature setup afterward. Retained assistant columns use the same owned upgrade.

The assistant is ordinary persistent chat around the existing Agent APIs. It has
no workflow. Langflow remains the owner of workflow records that its tools save.
See the canonical application-assistant contract in specs PR424.

Owner feedback supersedes the proposal's fixed model/effort binding: each message
may select a discovered model and effort on the same native Codex thread. Its
selection is immutable after reservation and participates in retry identity.
Conversation fields retain the latest admitted selection as composer defaults.
Existing retained message rows receive nullable selection columns on startup;
their original prompts, outcomes and idempotency digests are preserved.
This runs before Langflow's shared-metadata consistency check; creation of fresh
upstream tables remains upstream-owned.

Conversation renaming uses an owner-scoped `PATCH /conversations/{id}` with a
nonblank title of at most 80 characters. `AssistantStore.rename` rechecks session
authority inside the write transaction and changes only the title and timestamp;
it never starts or resumes inference. The chat heading supports double-click or
keyboard activation, Enter to save and Escape to cancel.

| Module | Objects and responsibilities |
| --- | --- |
| `models.py` | Typed requests/declarative graphs and concern-owned database rows. Conversation, message and draft receipt identities are durable; credentials are not. |
| `catalog.py` | `ComponentCatalog` reads already installed metadata, describes safe static fields and compiles declarative nodes/edges. It never loads component code or calls update/build hooks. Missing full metadata refuses. |
| `persistence.py` | `AssistantStore` owns conversation/message reservations and bounded history in the application database. Every operation is owner-scoped. |
| `workflows.py` | `WorkflowDrafts` uses Langflow Flow rows, database write/row locking, revision checks and atomic draft-plus-receipt transactions. It cannot run/publish/delete a flow; separate graph actions gate edits/runs on human approval. |
| `mcp.py` | `AuthoringMcp` exposes thirteen real FastMCP tools; proposal/read tools cannot approve actions. Host credentials bind owner/conversation/message/attempt; the model cannot select them. |
| `runner.py` | `AssistantRunner` composes a dedicated existing provider runner with an app-owned source workspace and private state. It supplies no repository/publication authority. |
| `runtime.py` | `AssistantRuntime` composes lifetimes, dispatch, native MCP connections, revocation, Activity and reconciliation. |
| `routes.py` | Authenticated application HTTP adapters. Late responses and tool writes recheck profile authority. |
| `settings.py`, `errors.py` | Explicit host configuration and stable safe refusal categories. |

The browser supplies only conversation/message IDs, text and supported model
choices. It never supplies host paths, owner IDs, runner URLs, credentials or
raw executable component templates. Only persisted save receipts create draft
cards. Opening the editor is an explicit new-tab action. Tests using fake native
receipts are controls; live provider/MCP/editor acceptance is separate.

## Human-approved graph actions (#291)

`graph.py` defines `GraphEditor`: `apply(data, changes)` returns an edited deep copy
and a bounded plain-text change preview, preserving existing private fields,
component code, IDs and layout; it composes catalog-owned value/port validation.
`actions.py` defines `WorkflowActions`: `propose` records an idempotent revision-
bound pending action, `read`/`list` project safe owner-scoped state, `decide` accepts
only authenticated human app decisions and atomically edits or claims a run, and
`execute` invokes the existing caller-aware Langflow execution path once. Restart
recovery marks interrupted run claims unknown, never replayable.

Canonical request/patch/action-row models belong to `models.py`. `AssistantStore`
creates only its owned action table. Runtime binds the originating app session,
tracks execution tasks separately from native assistant turns and exposes safe
outcomes. `AuthoringMcp` may propose/read only; approval is exclusively an app
route. `GraphActions.tsx` renders server-built previews and labelled Approve/Reject
controls; wire types stay in frontend `models.ts`. A human approval itself never
submits a model turn. Publication and native permission modes remain excluded.

Approval presentation uses server-derived Rename/Edit/Run categories. Rename is
only a name-only patch; settings, nodes, connections and mixed patches are Edit.
The model supplies a short plain-text description, bound into the request digest;
it never determines the category or authority. Technical identities remain in backend receipts; the card foregrounds the operation.

`AssistantGraphPermission` records human-granted Rename/Edit/Run consent for any
owned graph within one conversation and originating app session. `decide` creates
consent only on an admitted Always approve decision. `propose_graph_action` checks
that consent inside the same authority/revision/claim transaction, never from
model wording. `permissions` lists safe categories; `revoke_permission` serializes
revocation with decisions on the conversation lock. No cross-conversation consent.

`AssistantStore.delete_conversation(owner, identifier, session_key=...)` locks
the session and owned conversation, refuses active/unsettled messages or executing
graph actions, then deletes its message snapshots, action/draft receipts and
permissions atomically. It clears owned successor links and never deletes Flow
or independent run history. The authenticated DELETE route is app-only; MCP
does not expose deletion. Row locking serializes deletion with Send/approval.

Conversation deletion is from Laomedo history only; native provider thread/session
records are outside its scope. The confirmation makes no provider-erasure claim.

## Built-in native commands (#293)

`native.py` owns `NativeCommands.propose`, `read`, `list` and `decide`: proposals
bind the observed native catalog/run/thread and the originating app session;
`decide` reserves the exact command message and claims its action in one database
transaction. `AssistantStore.reserve_message` is shared by ordinary Send and native
approval under the existing conversation lock. Active chat work refuses approval
without consuming the proposal. There is no native-command Always grant.
`AssistantNativeAction`, `NativeCommandRequest` and `NativeActionDecision` belong
to `models.py`; `AssistantMessage.native_action_id` is an internal persisted mode,
not a browser-supplied MessageRequest field. Revocation, Stop and reconciliation
use the existing chat attempt lifecycle. Unknown outcomes never dispatch again.

MCP provides list_native_commands, list_native_agents, propose_native_command and
get_native_action. The model cannot approve or run an arbitrary RPC/shell command.
Native agents are explicitly unsupported in this Codex-first slice. The current
admitted built-ins are status, mcp, skills, review and compact. Review operates on
the assistant scratch workspace, not the user's repository. Review and compact
can use model quota. Native result messages are sent bare only after approval;
normal prompts retain the assistant wrapper. Commands may use the same scoped
MCP tools; any resulting graph/native proposal still needs its own approval.

Native catalogs and their provider-owned availability projection cross through
normal runner status, with run/thread binding and shared typed wire models. App
code never reaches into a concrete provider object. A missing or invalid catalog
is unavailable, not a fabricated empty list. The registered commands4 image
contains the explicit native-command adapter hook. Existing tool manifests remain
frozen for a native session. Older retained conversations/runs may require a new
conversation after this image upgrade; their history remains readable, and no
failed resume silently starts a fresh thread.

Explicit compact execution can complete on an ordered native contextCompaction
start/completion pair with the same observed thread, turn and item IDs. It retains
that evidence separately from a model-turn result, drains briefly for late native
failure, then uses normal cleanup. No assistant text or usage is manufactured.
Ordinary prompts and review still require native turn completion.

Native command discovery and dispatch require the adapter handshake flag
`nativeCommands: 1`. Base-only adapters remain valid for ordinary execution but
expose no executable command catalog and refuse explicit command requests before
any prompt. Image tags or advertised slash-command descriptions alone do not
establish handler support. Unknown capability fields and invalid flag values fail
initialization.


## Additional provider composition (issue305)

### Human-entered slash commands

`NativeCommands.submit` accepts commands only through authenticated app routes.
It binds the observed catalog, owned run/thread and stable operation key, retaining
a durable action under the conversation transaction. Sending an exact native
command or skill through this human-only route is the user's approval. It shares
`NativeCommands._reserve` with proposal approval and uses `dispatch_reserved`
after committing the action and message together, without a second confirmation,
independently of provider, name, arguments or model-use classification. MCP
proposals still require a separate human decision and cannot enter this route.
Discovery uses
the retained session catalog; no session is created or inferred by the picker.

Conversation provider and saved-account epoch are immutable. `AssistantRuntime`
keys its clients and locks by owner, provider, account and generation. The shared
saved-account manager constructs each provider with its admitted private profile;
chat never receives a credential or host profile path. Each provider owns command
catalog policy and terminal receipts; shared slash syntax does not imply shared
command support.

## Status before the first prompt

`MessageRequest.initial_native_command` distinguishes an explicit first `/status`
from a model prompt and is included in message identity. It is admitted only for
a fresh Codex conversation and persisted on `AssistantMessage`; `_job` forwards
the exact task and mode, without assistant instructions. The existing start,
observation, cancellation and reconciliation owners handle it. The actual native
status result renders and exports through the common status path; it creates no
approval proposal or model turn. Later commands retain observed catalog binding.

## Saved provider account selection

New conversations explicitly select a profile-owned saved connection and its
observed generation. `ConversationRequest` carries only that opaque selector;
`AssistantConversation` retains it immutably. Unbound history remains readable,
but cannot dispatch. A missing, foreign, changed or disconnected account never
falls back to a service account, host token or another saved account.

`AssistantRunner` uses `ProviderControllers.assistant_endpoint()` and its guarded
HTTP gateway. The shared manager owns startup, inventory, cancellation,
disconnection and restart recovery. Each connection generation has a separate
assistant runner and scratch source, independent of the graph runner/source.
Closing the chat adapter does not close the shared manager. Provider account
selection is visible before model discovery; existing chats show their binding.

The browser uses its native HttpOnly session cookie without a bearer override;
saved-connection lease checks remain enforced. Existing unbound chat runs are not
migrated or silently abandoned: new assistant dispatch is blocked while their known
runner roots retain active records, unresolved resumes or resource receipts.
Settled history stays readable and files stay untouched. New chats use saved
accounts; disconnected conversations remain readable but cannot change accounts.

The transition check never prevents app, Settings or graph startup. Read retained
history, including unknown in-flight outcomes, without dispatch. To reconcile old
operational state, use the pre-transition checkout (`872c4064`) and its original
private runtime and account to observe/cancel the exact old run; do not copy its
credentials or mark files settled manually. Restart the updated app after that
runner confirms cleanup. This bounded transition check can retire once all older
operational state is explicitly reconciled.

`ModelCatalogCacheEntry` retains a canonical catalog under the exact owner,
provider, connection, generation and runner instance. Cached composer reads never
open native discovery during an active chat. Every read still checks saved-account
admission; runner replacement invalidates the observation. Native execution still
validates the actual model options before prompting.
