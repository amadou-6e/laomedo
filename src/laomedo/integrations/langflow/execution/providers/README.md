# Saved-provider graph execution

This capability adapts the shared isolated native worker to saved Agent accounts
and anonymous public Issue reads. It never starts a native Langflow application
inside the account broker. The isolated worker has no network, host mounts,
Docker socket, account stores, runner tokens or review grants.

## Layout and responsibilities

`models.py` owns the credential-free `ProviderWorkerJob`, per-vertex virtual
routes and private request/reply envelopes. The parent binds the job's pipe to
`ProviderGraphRuns`; its actual capability never crosses into the worker.
`channel.py` owns `ProviderWorkerChannel` and its local HTTP-compatible adapter.
The adapter forwards only this job's virtual vertex/path/body on the private
pipe; it cannot open a host URL. `native.py` specializes `NativeGraphWorker` so
the same catalog/digest/constructor checks run before component instantiation.

`dispatcher.py` owns host-only `ProviderGraphDispatcher`: it derives profile,
account generation, model/effort, source run and host request UUID from the
approved plan. Starts use the controller's gated native reservation. Review
staging keeps patch bytes, native requests and grants in the host; only the
semantic hash reaches the worker. Reads and cancellation resolve only a run
acknowledged under the requested vertex. Worker aliases never become native
request authority. Anonymous Issue dispatch uses only a host-approved public
selection and the credential-free REST transport.

`admission.py` owns `ProviderGraphAdmission`. It derives the plan from the actual
effective graph and trusted host catalog, then separates profile-owned account
bindings from the credential-free execution snapshot. Only supported native
text/prompt plumbing, fresh saved-provider nodes and anonymous public Issue reads
are admitted here. Review sources come from exact Run Reference edges. Account
IDs, local authoring bindings and account-choice metadata stay on the host.
Unsupported resource/operation edges refuse instead of falling back to another
execution path.

The pinned local Skill path uses the existing `LaomedoSkill` reference output and
canonical `SkillReference` model. `ProviderGraphAdmission._skill` verifies the
configured imported registry's immutable revision; `_node` derives Agent Skill
bindings only from a direct `Skill.skill` -> `Agent.skill_reference` edge. Source
URLs, private connections, incoming edges and operations are unavailable here.
The reference component performs no I/O on this admitted path. Registry contents
stay on the host; the graph worker receives only public identity/hash references.
`GraphNodePolicy.native_request` checks exact singular/list reference equality
before native preparation; Claude verified-review targets still forbid Skills.
The host materializer rechecks bytes before a model starts.
`ProviderGraphAdmission.check_resources` rechecks registry availability at output
release without rewriting a completed native outcome. The imported registry is
the existing host-wide local registry exposed by assistant Skill discovery;
this path does not expand private GitHub Skill-source access across profiles.
Registered MCP execution is a separate host-owned boundary. `GraphMcpSelection`
in `models.py` retains the existing canonical resource binding, installed node
identity, registered name and exact Agent targets. `RegisteredMcpTools` in
`mcp.py` checks profile/lease/server/version without releasing configuration
during readiness. Only an approved run decrypts the selected registration and
opens its native transport. Native STDIO/SSRF policies remain mandatory.
The resource owner's constructor retains the admitted plan without opening a
transport; the tool adapter's constructor pins only its audited native descriptor.
Native HTTP policy refusals become `McpError` at this resource boundary, without
exposing HTTP details or weakening the policy.
`prepare` creates invocation-local native clients and exact per-Agent manifests;
`check` fences discovery, each tool call and output release; `close` revokes its
registrations before closing only its owned clients/session managers. Tool
arguments and results are not copied into new activity records.
`check_saved_graph` permits data-only autosave of name-only owner/version-pinned
references, including unconnected draft nodes. It rejects embedded configuration
before native Flow persistence can stage credentials. Execution additionally
requires every selected MCP node to have an admitted Agent target.

The execution projection removes registered MCP selection nodes and their tool
edges from the worker graph: their host owner resolves them, without evaluating
MCP component code in the credential broker. The approved selection digest stays
bound to the host plan; the worker separately verifies its projected graph.
`GraphNodePolicy.native_request` rejects worker-supplied manifests/registrations
and injects only the host-prepared registration. Request aliases and cancellation
correlation describe worker intent, not native credentials or tool authority.
For MCP sources the worker-visible request hash covers that validated intent;
native history retains the separate semantic hash including the approved tool
manifest. Host review provenance is recomputed from native workspace snapshots,
never inferred from the projected hash. `check_dispatch` repeats metadata and
account-generation checks on the app loop before a worker-thread start.
It refuses calls from that loop itself rather than blocking it. The admission
owner's `check_mcp_parameters` rejects connection overrides before persistence,
including drafts that have not selected a server; empty selection is not a way
to retain headers or other connection settings in flow data.
The resource owner keeps queued, unclaimed registrations alive while earlier
nodes run. `_maintain_registrations` rechecks live authority before calling the
registry's unclaimed-only renewal; native claimed-run heartbeats stay independent.
`close` cancels that supervisor before revoking grants and closing clients.
Verified-review Claude targets cannot acquire external tools. No endpoint,
command, header, credential or native client crosses into the graph worker.

Text-only graphs use the same isolated worker and browser lease without granting
any Agent authority. The fixed native Combine Text component joins instructions
and external Issue data before the Agent task; posted code cannot add a component.
Readiness dry-plans this deployment's supported graph without creating a Job,
issuing a graph capability or starting an Agent. Unsupported resources therefore
remain visible before a user approves a run.

`catalog.py` owns `ProviderComponentCatalog`. It builds metadata only from fixed
operator-installed classes and component files at startup. It never accepts a
browser component dictionary, component path or Python string for evaluation.
`ProviderGraphCatalog` extends only host selection admission with `MCPTools`;
the shared GitHub worker catalog still refuses that class. MCP metadata uses
the installed native Component base without running the transport constructor.
The same immutable host snapshot supplies assistant authoring and worker code
identities; worker-produced metadata cannot establish trust.

`executor.py` owns `ProviderGraphExecutor`: the API-only broker injects this
backend into existing assistant actions. It verifies the current browser lease,
uses the approved Flow snapshot and exact run UUID, admits one private worker,
and returns the existing native RunResponse shape. It retains supervisors whose
native cleanup remains uncertain. Neither worker output nor a retained request
can grant a new run or substitute a saved account. All provider vertices must
complete; conditional provider execution is not supported in this initial path.
The existing native Job UUID is the durable execution replay barrier. Its metadata
retains only host-observed terminal node outcomes and explicit native cleanup
confirmation, so existing assistant diagnostics can read partial completion
without treating a worker message as evidence. Actual node outputs keep the
existing bounded assistant evidence owner. Revoked cleanup receipts are currently
memory-only; host restart relies on the native controllers' durable recovery and
does not replay a graph or restore its admission.

`browser.py` owns the curated canvas run adapter. It authenticates the current
browser, authorizes the owned Flow, validates the exact canvas snapshot and runs
only the same isolated executor. Native AG-UI adapters render job-scoped progress;
native graph builders are never imported as an execution fallback. Disconnect or
an owner-scoped Stop cancels that exact local task and retains uncertain cleanup.
Unsupported execution modes and resource overrides refuse before dispatch.
`ProviderCanvasResponse` explicitly closes its execution iterator when ASGI send
fails or disconnects. A task completion callback removes the active receipt even
if the consumer cannot finish. `ProviderCanvasProgress` drops excess observations
and reports the count; a stalled consumer cannot abort the underlying run.

The canvas API contract is deliberately narrow:

| Route / outcome | Response |
| --- | --- |
| `POST /api/v2/workflows` with native `WorkflowRunRequest`, mode `stream`, protocol `agui` | 200 SSE using the installed AG-UI adapter; terminal success requires host execution completion. |
| `POST /api/v2/workflows/stop` with native `WorkflowStopRequest` | 200 native `WorkflowStopResponse`, cancellation requested; no claim of native settlement. |
| Missing authentication / wrong origin | Native auth 401/403, or 403 `provider_request_refused`. |
| Foreign/absent Flow or active Stop receipt | 404 without disclosing the other owner's state. |
| Body exceeds 16 MiB | 413 `assistant_input_invalid`. |
| Malformed body / unsupported configuration | 422 `assistant_input_invalid` / `isolated_graph_unsupported`. |
| Mid-stream execution failure | AG-UI `RUN_ERROR` with a sanitized host machine code or fixed runtime fallback; no raw exception text. |

Worker progress and output text are observations, not proof of workspace changes.
Before worker startup, the executor drains a zero-turn native catalog preflight
for every selected account, including on cancellation. No Agent can start before
all pinned model/effort choices pass. `ProviderGraphDispatcher.failures` retains
only the first sanitized host machine code for each vertex/action; the existing
Job metadata records these refusals without task text, exception strings or paths.
If the worker fails, the graph reports the code from the last retained refusal;
metadata preserves the first refusal for each distinct vertex/action pair.
The canvas may show a sanitized host failure code instead of the generic runtime
code; worker messages cannot select that public code.
The host's acknowledged native records decide Agent completion; the independently
verified snapshot-derived patch remains the evidence supplied to the reviewer.

`ProviderWorkerEvents` in `channel.py` forwards only native build-start/end events
on the existing private job pipe. These events describe the worker's progress;
they grant no native authority. Host-observed Agent terminal records still decide
whether a graph completed. The shared native driver owns graph construction and
accepts an optional event manager, avoiding a second graph execution loop.
`ProviderProgressGraph` observes the native batch vertex operation because LFX's
batch runner does not emit the start/end events its sequential runner provides.
The native scheduler, parser checks and vertex results remain the shared owners.

`activity.py` owns `ProviderGraphActivity`, the host-only bridge to the existing
Activity store/capture. It reserves exact profile/flow/job/vertex identity before
dispatch and binds only host-acknowledged native run/attempt IDs. It reads the
existing exact native controller, never a worker URL or worker-provided identity.
The same normalized attempt projection powers the existing read-only Activity UI.
After dispatch, observation failures are retained best-effort and never replace
the native execution outcome. Cleanup seals any reservation not yet bound to a
native attempt, including when cancellation arrives before the first status poll.

`container.py` specializes the shared sandbox supervisor hooks and private
exchange. It validates the actual graph, checks lease/deadline while requests
are active, revokes before cleanup, and cancels only this job's native request
receipts. The shared supervisor remains the single owner of container hardening,
lease registration, inspection and exact cleanup. Normal native run history
survives job revocation; unknown cancellation is never claimed as settlement.

The fixed catalog reports `allow_custom_components=false`. Native editor refresh
POSTs receive an explicit 403 understood by the existing frontend, before any
body is read; posted component code is never evaluated. Configuration choices
remain available through the audited authoring MCP tools.

The selected source must be a clean subdirectory inside a Git tree, matching
the native runner's source contract. Keep repository metadata outside that
subdirectory; startup rejects a detached export before any model submission.

The broker passes one host-owned `McpSettings` object to its registry and native
controllers. Each provider passes that object to `BaseAgent`, whose MCP admission
reads only that fixed private rendezvous directory; request bodies cannot select it.

This integration is under development. The ordinary native-process review
binding remains disabled until the isolated app and actual graph path are
verified. Host policy/dispatcher tests are separate from real container and
model-backed end-to-end acceptance.
