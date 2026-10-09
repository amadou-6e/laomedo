# Phase G: durable Langflow-to-runner identity join

This is a credential-free design and test protocol for the remaining #22/Q11
trace gap. It is not evidence that the join is implemented. It uses the pinned
Langflow 1.12.3 image and the saved five-node Codex flow. No model call or
change to the live runner configuration is required for the first gate.

## Identity source

The custom component can read `self.graph.run_id` and its configured node ID
through `self._vertex.id` in pinned Langflow 1.12.3. These are runtime internals,
not a stable public identity API. Two independently constructed
`Graph.from_payload` executions produced distinct graph run IDs and the same
stage ID. A follow-up attempt to call `arun` twice on the same graph object
dispatched the component only once; it did not prove a new ID for a reused
graph. The in-process route exposed `graph.flow_id=None`; a flow ID must remain
unknown unless the installed server supplies it. The test must establish
whether separate browser Playground builds reuse the same graph run ID and
whether that ID appears in Langflow's durable build or trace record. If it
repeats or is not durable, the Laomedo-minted invocation ID is the primary
identity. A node-readable value alone is not a verified cross-store join.

## Required record and ordering

Before the first runner POST, persist one Laomedo workflow run ID, trace ID, graph
revision, configured stage ID, invocation ID, graph run ID if supplied, and the
exact runner request ID and canonical request digest. A write failure refuses
dispatch. The runner's first valid acknowledgement then binds its provider,
run ID, and private raw-event reference to that invocation. Store cancellation
request, terminal runner confirmation, and partial-event availability as
separate receipts. The same identities must reopen after restarting the
Langflow/Laomedo process. The Laomedo invocation ID remains authoritative even
when Langflow supplies its own run ID. An uncertain POST is reconciled only by
read-only lookup of the reserved request ID, never by generating a new one.

The existing `WorkflowRunStore` and `RunnerTraceBridge` already implement this
order for a synthetic controller. Phase G must make the actual Langflow custom
node use that durable boundary, or prove a different boundary has the same
ordering and conflict semantics. A runner-only metadata field is insufficient:
it cannot by itself show the Langflow-side reservation or restart behavior.

## Credential-free gates

1. Run the pinned in-process identity test and inspect the installed server's
   saved-flow/Playground build identity, including two builds of one saved flow.
   Record which ID is durable in Langflow and which is only process-local. Do
   not infer a flow ID in the direct graph. On any Langflow image change, rerun
   this identity test and refuse the join if routing differs.
2. With a fake runner, hold the async acknowledgement and kill the Langflow
   process at three points: before the pre-dispatch write, after the write but
   before POST, and after POST but before acknowledgement binding. Reopen the
   store. Assert zero, zero, and at most one runner start respectively. The
   third case must retain an explicit unknown outcome and permit only read-only
   reconciliation by its original request ID; no case may redispatch.
3. Test exact duplicate acknowledgement, altered request digest, mismatched
   provider/run/raw-event reference, cross-invocation binding, Stop before
   acknowledgement, Stop after acknowledgement, terminal status, and late
   partial events. Every receipt must retain the same trace and invocation IDs.
4. Verify the saved flow's embedded component code equals the tested source,
   and verify a fresh installed-server run through that flow. Keep the runner
   fake so these gates spend zero model turns.

Only after these gates and an independent review may a separately bounded real
turn test join the browser Stop route to the reopened durable record. That test
must check actual runner IDs and private raw-event references, not timestamps
or coincident statuses. The shared ledger is 6/12 before Phase G, leaving six
reserved slots available but authorizing no automatic submission by this page.

The earlier Phase E and F Stop observations remain valid at their stated scope.
They do not become cross-store trace passes retroactively.
