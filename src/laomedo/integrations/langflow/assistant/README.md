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

| Module | Objects and responsibilities |
| --- | --- |
| `models.py` | Typed requests/declarative graphs and concern-owned database rows. Conversation, message and draft receipt identities are durable; credentials are not. |
| `catalog.py` | `ComponentCatalog` reads already installed metadata, describes safe static fields and compiles declarative nodes/edges. It never loads component code or calls update/build hooks. Missing full metadata refuses. |
| `persistence.py` | `AssistantStore` owns conversation/message reservations and bounded history in the application database. Every operation is owner-scoped. |
| `workflows.py` | `WorkflowDrafts` uses Langflow Flow rows, database write/row locking, revision checks and atomic draft-plus-receipt transactions. It cannot run/publish/delete a flow. |
| `mcp.py` | `AuthoringMcp` exposes six real FastMCP tools. Host credentials bind owner/conversation/message/attempt; the model cannot select them. |
| `runner.py` | `AssistantRunner` composes a dedicated existing provider runner with an app-owned source workspace and private state. It supplies no repository/publication authority. |
| `runtime.py` | `AssistantRuntime` composes lifetimes, dispatch, native MCP connections, revocation, Activity and reconciliation. |
| `routes.py` | Authenticated application HTTP adapters. Late responses and tool writes recheck profile authority. |
| `settings.py`, `errors.py` | Explicit host configuration and stable safe refusal categories. |

The browser supplies only conversation/message IDs, text and supported model
choices. It never supplies host paths, owner IDs, runner URLs, credentials or
raw executable component templates. Only persisted save receipts create draft
cards. Opening the editor is an explicit new-tab action. Tests using fake native
receipts are controls; live provider/MCP/editor acceptance is separate.
