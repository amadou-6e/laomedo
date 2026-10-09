# Phase G join boundary candidates

This file records the candidate before its first installed-runtime check.
Claude's first review rejected the pre-graph host reservation for visible
Playground Send. The corrected candidate below moves reservation to the first
component-to-host bridge call. A later [credential-free installed probe](PHASE-G-JOIN-RESULTS.md)
tested that route with a fake native runner; the real-agent and restart gates
remain open.

It follows the [Phase G protocol](PHASE-G-CORRELATION-PROTOCOL.md) and the
[zero-model server identity observation](PHASE-G-IDENTITY-RESULTS.md).
The user-selected local permission profile, Docker settings and provider login
remain as they are. No extra human sign-in is introduced.

## Unresolved launch boundary

The host-first sequence below works only when Laomedo launches the graph
through `FrozenLangflowStage`. The passing visible Stop tests instead start
from Langflow Playground; no Laomedo host controller runs before that graph.
`FrozenLangflowStage` has no hook in that request path. The pinned Langflow
`Graph.arun` forwards execution to its `Coordinator`, whose `run` hands the
graph to an executor. The inspected coordinator methods expose no pre-node
reservation callback. Consequently, the host cannot reserve a verified
graph/invocation before a Playground Send or know the dynamic task body then.
The component's first call to a host bridge is the proposed pre-runner-POST
seam. Its dispatch and cancellation behavior still needs a credential-free
installed-runtime test before this route is selected.

The pinned image source confirms that a saved revision cannot automatically
stand in for the executing graph. Langflow 1.12.3's v1 `build_flow` accepts
request `data` and forwards it to `start_flow_build` (`api/v1/chat.py`, lines
304-318 and 408-466). Its v2 background workflow request also carries
`parsed.data` to the worker (`api/v2/workflow.py`, lines 699-728). This source
shows an inline graph path exists; it does not establish which path the tested
Playground Send used or attest the graph loaded by that run.

Two candidates require a credential-free comparison before selection:

1. **Host-launched graph:** retain `FrozenLangflowStage` and its verified
   graph/code hashes, then attach `RunnerTraceBridge` to that execution.
   This can establish a durable join for a host launch, but it does not cover
   the visible Langflow Playground Stop route without a separate UI launch
   integration.
2. **Lazy host bridge at component dispatch:** the component calls a host
   controller with its resolved task and pinned skill references. The host
   reserves the run and request before contacting the runner. This covers a
   visible Playground Send without a pre-graph hook. The host can independently
   inspect the saved flow revision, but cannot yet attest that those bytes are
   the executing editor graph. A pinned Langflow build hook is a possible later
   route to that stronger claim; it is not a prerequisite for a durable runner
   join if the weaker identity label is explicit.

Both candidates need an actual restart observation and a separate trusted
controller. The following sequence is the proposed lazy-bridge target, not an
instruction to alter the current server configuration.

## Trusted and untrusted owners

The host controller owns `WorkflowRunStore`, exact runner request construction,
the runner API token, and the authoritative cancellation/terminal receipts. At
the first bridge call it may fetch and hash the saved flow and embedded
component code, but it must label this the **saved revision**, not the
executing graph. `FrozenLangflowStage` attests a graph only when it launches
that graph itself, which Playground Send does not do. The Langflow graph and
its custom component remain
execution code: they may request work and observe a result, but their stdout,
return value and self-reported status cannot attest a runner completion. The
host compares a native runner status with the one exact binding it persisted.

The component's first bridge call carries a client-generated idempotency UUID,
the resolved task, pinned skill references, configured stage ID and any
observed `graph.run_id` and `graph.flow_id`. The bridge uses a private
authentication token and applies the existing local run limits. That token is
an access control for this local prototype, not a separate operator sign-in
or a same-user security boundary. The host binds the idempotency UUID to the
exact input digest, validates the request, mints a distinct Laomedo run,
trace, invocation and runner request ID, and durably freezes the canonical
runner body digest before the first runner POST. An identical client retry
looks up the original reservation and never starts a new run; a changed body
under the same UUID is a conflict. If any write fails, dispatch is refused. A
crash before this bridge call creates no runner start. A crash after
reservation but before POST leaves a reserved, never automatically dispatched
record.

The observed Langflow IDs are self-reported correlation context. The host must
not claim they verify the graph revision. It records the independently fetched
saved-flow revision separately, with `executing_graph_verified=false` until a
trusted Langflow build boundary can attest the actual payload. The minted
invocation ID is the primary cross-store identity. The host sends only the
frozen request to the runner.
It accepts one early acknowledgement only when request ID, request digest,
provider, runner run ID and private raw-event reference match. It commits that
binding in `WorkflowRunStore` before telling the component a run ID. An
uncertain POST remains unknown and can only be reconciled by the existing
read-only request lookup. A changed body or conflicting acknowledgement fails.

The component's Stop path asks the host bridge to cancel by the original
client idempotency UUID, even if the first bridge response has not arrived.
The host resolves that UUID to exactly one reservation. A reserved invocation
with no runner POST becomes `cancelled_before_dispatch`. If the POST outcome
is uncertain, the host performs only a read-only lookup by the frozen runner
request ID, then cancels the exact runner run ID if found. A missing or
conflicting lookup remains unknown; it never triggers a second POST. The host
records request, terminal status, native event reference and teardown evidence
as separate receipts. A client disconnect or Langflow `JOB_FAILED` does not
mean native cancellation. The component can render the host's result but does
not set `evidence_complete` or claim semantic success.

## Storage and restart boundary

The current disposable Langflow image defaults to a SQLite file under its own
site-packages tree. The previous `/app/langflow` test mount was empty. A restart
probe needs a private mounted database location selected explicitly for the
disposable server. The proposed test-only setting is
`LANGFLOW_DATABASE_URL=sqlite:////app/data/langflow.db` with a private host
directory mounted at `/app/data`. This changes no existing long-running server.
The host `WorkflowRunStore` remains in its own private state outside Git.

After killing and restarting the Langflow process, reopen both stores and
compare the saved-flow identity with the Laomedo invocation and exact runner
binding. Langflow's trace must be located by a verified key such as its saved
flow and session identity; Phase G found graph run IDs only within payloads,
not as primary trace keys. Matching payload IDs are corroboration only. If a
Langflow record is absent, label that side unknown; do not fabricate a
cross-store join from coincident times or copied text. The
host may mark a backend-dead graph terminal/incomplete, but must never
redispatch its runner request automatically. #93 still owns independent lease
and external-write revocation during a wider outage.

A reservation stranded before its first POST is reported as
`reserved_not_dispatched` after restart and can be explicitly cancelled; a
same-UUID retry retrieves that record without starting it. A new Playground
Send after a backend crash creates a new client UUID and a new invocation. It
is a user-initiated run, not an automatic redispatch of the old one.

## Test sequence and failure conditions

1. Credential-free unit tests exercise pre-dispatch write refusal, exact
   acknowledgement and idempotent replay, altered digest, cross-invocation
   run ID, malformed raw-event reference, Stop-before-ack, terminal-after-Stop,
   and reopen without a second POST. Test Stop using only the client UUID,
   including before bridge acknowledgement and during an uncertain POST. Test
   lost bridge response with the same client UUID and a changed-body conflict.
   Keep the legacy direct runner clients unchanged.
2. In the pinned disposable Langflow server, run the saved flow against a
   fake runner and inject process death before reservation, after reservation
   but before POST, and after POST but before acknowledgement binding. Verify
   zero, zero and at most one starts, respectively. The last state stays
   explicitly unknown until read-only reconciliation. No model turns.
3. Kill and restart the server using the test-only private database mount;
   inspect a real Langflow trace ID and the reopened Laomedo binding. Verify
   graph/flow/stage/request/runner IDs and exact raw-event reference without
   reading or committing transcript contents. No model turns.
4. Only after these tests and a substantive independent review, run one
   separately frozen real-turn browser Stop case under the shared 12-turn
   ledger. No new login handoff is needed. Timeouts count. Do not spend the
   remaining six slots merely to repeat the already-passing Phase E/F tests.

No existing issue state or PR maturity changes merely because this design is
written. A persistent server configuration or a new bridge service requires
its exact deployment settings to be reviewed before activation.
