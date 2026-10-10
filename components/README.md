# Laomedo Codex Agent for Langflow

Operator-installed custom component for pinned Langflow 1.12.3. This wraps the
existing local Docker Codex runner; it does not replace Langflow's built-in Agent
or implement its tool interface. The `LaomedoRunner` embedded in
`examples/skill-agent-pilot/pilot-flow.json` now uses the same private runner
API token; its historical model-turn evidence predates that change.

## Output Contract and precheck

`LaomedoOutputContract` exposes pinned Precheck Requirements and Validation
Outcome Data ports. Install this repository's Laomedo package in the Langflow
runtime before loading it: the node and Codex requirements input import the
same `laomedo.output_contract` evaluator used by the host runner. Mounting only
component files is insufficient for this component. A missing package fails
visibly at import rather than falling back to a different validator.

Use one requirements-only instance before the Codex node and a separate
validation instance after its Submission output, configured with the same JSON
form. This avoids a cycle in Langflow. The validator rejects a missing or
different requirements revision, retains task outcome separately from validity,
and emits accepted/rejected Data for conditional routing. Invalid form settings
are configuration errors; invalid submissions are routable rejections.
Connect the Codex Submission port to Agent Submission on the validator. Its
legacy Run Reference port is not a submission envelope and cannot replace it.

The native Codex dynamic precheck tool returns bounded path/code feedback within
a request. A completed invalid form can receive one additional same-thread
continuation by default, configurable from zero through eight. Continuations
count against the existing operator-set model-turn ledger. Task failure,
uncertain execution, external-write capability, command/file-change receipts
or unknown tool effects do not trigger automatic correction. Consequently a
coding task that already ran commands normally routes its invalid form to the
graph rather than automatically repeating work. Infrastructure retries remain
separate. Credential-free tests establish the transport and evaluator behavior;
live Codex/model acceptance is not claimed by these tests.

Mount this directory read-only into the Langflow container and configure
`LANGFLOW_COMPONENTS_PATH=/app/custom_components`. The category package is
`laomedo/`, containing `__init__.py` and `codex_agent.py`. Restart the test server
after code updates; inspect its component catalog for `LaomedoCodexAgent` before
importing a flow. The runtime must have the existing local runner reachable at
`http://host.docker.internal:8765`; native local installations use localhost.

This is a proposed deployment configuration until the operator approves startup.
Keep the existing server and its data volume separate from the acceptance server.
Do not mount Codex credentials, native sessions, the Docker socket or private runner
state into Langflow. Mount only the private `api-token` file read-only and set
`LAOMEDO_RUNNER_TOKEN_FILE` to that path. The component needs the authenticated
loopback runner API.

## Inputs and outputs

Connect Laomedo Skill's Skill Reference output to the agent's Skill Reference
input. The Skill node takes an existing Skill ID and exact SHA-256 revision and
emits a structured reference; it does not load credentials, expose host paths or
claim that a revision exists. The runner resolves and verifies the immutable
whole bundle before a model turn. Inline advanced skill fields remain compatible
with older flows; conflicting wired and inline references fail explicitly.
When connecting a Skill node to an older saved flow, clear advanced Skill ID and
Skill Revision values if they conflict. Each bundle's `SKILL.md` frontmatter
`name` must equal its pinned skill ID to avoid ambiguous Codex discovery.

Fresh: supply task, immutable whole-skill ID/revision, model and effort.
Resume: set operation to resume and supply the prior structured Run Reference;
its completed status, thread, model/effort and exact post-run hash are required.
Connect Data to Prior Run, or paste its serialized object into advanced Prior Run
JSON for a manual/API invocation. Data handle inputs are not persisted inline by
Langflow's saved-flow builder; the JSON input is the explicit persisted alternative.
Status/cancel: supply a prior run reference containing its run ID; these submit
no model turns. Cancel requests retain the runner's status and evidence.

Answer is a Langflow Message; Run Reference is Data containing answer, run/thread
IDs, state, post-run hash, model/effort, skill revision/use evidence, artifact/trace
references, error category and unknown usage. Both outputs share one dispatch per
component build. A new explicit build submits a new request; automatic
infrastructure retry is not implemented. Output correction, when requirements
are connected, follows the separate bounded policy above. Trace references are
opaque identifiers, not raw transcripts.
For multiple skills, the legacy `skill_revision` and `skill_use_evidence` fields
are single-skill-only and may be empty; use the per-skill `skills` array.

Invalid input fails before HTTP. Runner failures raise errors naming known run ID
and category; transport timeouts cannot establish whether remote execution stopped.
For a known failed invocation, `RunnerResultError.run_reference` retains the
public run/thread identity, state and partial trace reference. It omits private
profile/workspace fields and does not turn failure into an Answer. A resume
transport timeout retains the known run/trace with an unknown outcome, without
retrying. Status and cancel remain available using that reference. Responses for
another run, or a completed resume naming another native thread, are refused.
The exception's structured reference is available to code calling the component.
The legacy Answer/Run Reference ports retain that exception behavior; existing
saved flows need no migration. Connect the new Submission / Outcome Data port
to an Output Contract or router to receive known runtime failures as data.
Selecting legacy ports too can still fail the graph; their exceptions are not
silently changed. All three ports share one dispatch within a component build.

The new port emits `schema_version: laomedo.agent-submission.v1`, `submission`,
`answer`, `task_outcome`, `executor_status`, `evidence_complete`, `run_reference`
and `error_category`, plus `requirements_revision` and `precheck`. The latter
contains a separately reported `installed` boolean and nonnegative `call_count`, or `unknown`
when unreported; a supplied form does not prove a precheck tool was called.
The requirement revision is null when unreported. `submission` is the JSON object in the agent's final answer,
or null for absent, malformed or non-object JSON. The reported `task_outcome`
is read only from that object's `task_outcome: success|failure` field; normal
prose and process exit never imply task success. An incomplete executor cannot
promote a success claim. A reported failure is routable even when the executor
completed. This port does not validate the form; downstream Output Contract
remains authoritative, and submitted content is untrusted result data.

The run reference retains native run/request/thread/trace references and, when
reported by the join bridge, invocation, Laomedo run and trace IDs. Missing IDs
remain null. Evidence completeness is the runner's exact boolean, or `unknown`
when unreported; snapshot readiness is not a substitute. A poll disconnect
retains the last bound run and partial answer/trace, sets executor status to
unknown and clears the artifact reference. A lost initial acknowledgement keeps
the request UUID without inventing a run or redispatching. Stable error codes
are emitted without copying raw exception text or unbound error identities.
There is no PR-reference field and no fabricated publication claim.

Input validation still refuses before dispatch. Framework cancellation from
Playground Stop still propagates so it cannot continue downstream execution;
an explicit cancel/status operation can supply its known runtime outcome to
the new port. Transport uncertainty is not permission to retry. No automatic
output correction or infrastructure retry is added by this port alone.
The fresh route uses early native acknowledgement, then read-only polling.
Bounded installed-runtime tests showed visible Playground Stop cancelling one
active Codex turn and one prepared turn. Do not infer a remote stop from client
interruption alone; the runner's exact terminal evidence is required.

## Opt-in Playground join prototype

The optional advanced Join Bridge URL routes a fresh/start component call
through a host-owned [join service](../laomedo/langflow_join_service.py). The
checked-in sample flow leaves this field unset, so its current runner route is
unchanged. The bridge takes a separate read-only token file in Langflow at
`/run/secrets/laomedo-bridge-token`; the host service reads its own copy, a
runner API token file and a private run store outside Git. The host independently
hashes the saved-flow export, reserves the run before its native POST, and binds
the client UUID, invocation, native request/run and trace. The saved export does
not attest the executing editor graph. Stop persists by client UUID even when
the first bridge acknowledgement is missing. The service is opt-in and has not
been activated for the existing server. While a Stop intent is pending, a
bridge status GET may reconcile the exact native request and send its cancel;
it never starts another native request.

The [develop-based checks](../experiments/exp117/RESULTS.md) compose visible
Stop with the durable host/native/Langflow join at both prepared and active
points, including a disposable SQLite restart with no redispatch. The active
probe retains an inconclusive classifier result plus a separately reviewed
retrospective failed-read explanation. Earlier independent results remain
archived. This bounded local observation does not attest the executing graph,
production authentication or orphan cleanup. The service remains opt-in; no
existing server is silently reconfigured.

## Checks

Run `python tests/langflow/test_codex_component.py` inside the pinned Langflow
image with this repository available. It uses a synthetic runner and no credentials
or model turns. Run the existing `python -m unittest discover -s tests` on the host as well.
Real imported-flow acceptance needs a separately authorized model-turn ledger.

The durable cross-store join and restart checks remain tracked in
[follow-up #22](https://github.com/amadou-6e/laomedo/issues/22).

Reference: [Langflow custom components](https://docs.langflow.org/components-custom-components).
Newer documentation features must be checked against the installed 1.12.3 runtime.
# Multiple skills

Connect several Laomedo Skill outputs to the agent's Skill References list port.
Each reference pins one whole immutable bundle. Up to sixteen distinct IDs are
supported; repeated IDs and mixed multi-reference/inline selections fail before
dispatch. The runner materializes all bundles before a turn and records each in
`skills`. Resume retains the original set. Availability is reported as offered,
not proof that the model used every skill. Existing single-reference flows remain
compatible. Two-node graph wiring and runner restart/resume are covered by
credential-free tests; a multi-skill model-backed turn has not yet been run.

## Explicit handoffs and bounded loops

`LaomedoHandoff` selects a completed origin answer/task and outputs provenance.
Connect both Task and Provenance to the next agent, and connect its Skill inputs
independently. Each fresh agent has its own workspace and native thread. Provenance
and selected artifact manifests persist in the downstream runner record.

`LaomedoBoundedController` implements bounded scheduling without cyclic visual
edges, persists turn reservations and partial outcomes, and exposes exact stop
reason/cancellation evidence. It requires the Laomedo runtime package on Langflow's
Python path and private execution storage. The separate deployment configuration
in [agent-handoffs](../examples/agent-handoffs/README.md) remains a draft.
Tests cover real graph builds with synthetic HTTP; the example also records one
successful real two-agent chain at exactly two authorized submitted turns.
