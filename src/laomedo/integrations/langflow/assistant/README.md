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
| `mcp.py` | `AuthoringMcp` exposes nine real FastMCP tools; proposal/read tools cannot approve actions. Host credentials bind owner/conversation/message/attempt; the model cannot select them. |
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
it never determines the category or authority. Exact server-built changes and
identities remain in expandable details, while the card foregrounds the operation.

`AssistantGraphPermission` records human-granted Rename/Edit/Run consent for any
owned graph within one conversation and originating app session. `decide` creates
consent only on an admitted Always approve decision. `propose_graph_action` checks
that consent inside the same authority/revision/claim transaction, never from
model wording. `permissions` lists safe categories; `revoke_permission` serializes
revocation with decisions on the conversation lock. No cross-conversation consent.
