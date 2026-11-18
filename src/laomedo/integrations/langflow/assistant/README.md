# Application assistant

Persistence, declarative metadata validation, atomic workflow receipts, MCP
hosting, direct provider orchestration and chat rendering form one application
feature. Controlled tests and real provider/editor acceptance are separate gates.

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
is unavailable, not a fabricated empty list. The registered commands2 image
contains the explicit native-command adapter hook. Existing tool manifests remain
frozen for a native session. Older retained conversations/runs may require a new
conversation after this image upgrade; their history remains readable, and no
failed resume silently starts a fresh thread.

Explicit compact execution can complete on an ordered native contextCompaction
start/completion pair with the same observed thread, turn and item IDs. It retains
that evidence separately from a model-turn result, drains briefly for late native
failure, then uses normal cleanup. No assistant text or usage is manufactured.
Ordinary prompts and review still require native turn completion.
