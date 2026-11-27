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

Text-only graphs use the same isolated worker and browser lease without granting
any Agent authority. The fixed native Combine Text component joins instructions
and external Issue data before the Agent task; posted code cannot add a component.
Readiness dry-plans this deployment's supported graph without creating a Job,
issuing a graph capability or starting an Agent. Unsupported resources therefore
remain visible before a user approves a run.

`catalog.py` owns `ProviderComponentCatalog`. It builds metadata only from fixed
operator-installed classes and component files at startup. It never accepts a
browser component dictionary, component path or Python string for evaluation.
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
| Mid-stream execution failure | AG-UI `RUN_ERROR` with fixed public runtime failure; no raw exception text. |

Worker progress and output text are observations, not proof of workspace changes.
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
