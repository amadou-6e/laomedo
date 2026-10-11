# EXP-123 amendment 01: concrete graph candidate

Frozen before candidate code and any case dispatch. The original protocol
remains historical. This amendment resolves the independent protocol review's
mechanism and timing gaps, and pins merged specs #297 at
`86d6fcff5c6d51e6ad106daf59f3f7036c7f9e8b`.

## Candidate and meaning of a pass

Use the pinned Langflow/lfx 1.12.3 `Graph.from_payload` and `Graph.arun` APIs in
one disposable worker container. Construct the graph from the exact embedded
component bytes and hash its JSON before dispatch. The graph has two distinct
synthetic agent nodes, two custom wait nodes, a conditional router after the
first wait, and terminal outputs. The failed branch of that router reaches
the second agent. A passing result excludes that branch. The two-invocation
cap is unrolled into the graph; this does not prove arbitrary Langflow cycles.

The wait component polls a synthetic loopback ingress store from within the
graph. Component code is permitted integration code. The controller invokes
`arun` once per case; it must never invoke an agent, restart the graph, or
dispatch a replacement graph in response to a check. A pass proves this
custom-component integration on the pinned engine, not built-in webhook
waiting or production GitHub ingress. Journal actual graph run identity,
component identity and invocation identity at each node.

## Fixed settings and cases

- Gate wait: 12 seconds measured with the worker's monotonic clock; poll every
  0.1 seconds; each loopback HTTP request times out after 1 second. Controller
  case deadline: 25 seconds. Post-terminal observation: 1 second.
- Synthetic repository `fixture/repo`, PR 1. Agent 1 returns head `1` repeated
  40 times; agent 2 returns head `2` repeated 40 times. Invocation identities
  derive from the fresh case run ID and the distinct node ID. Exactly one
  frozen graph and at most two invocation records are permitted per case.
- Each fixture carries case run, gate, PR, head, check and delivery IDs. The
  synthetic ingress validates a fixed fixture signature; journal accepted and
  refused deliveries. This is not a claim of GitHub signature verification.
- Deliver ordinary check fixtures after the journal records the corresponding
  wait, with a 0.2-second delay. A dedicated early-event case records a passing
  H1 fixture before dispatch. An unknown/pending fixture cannot route; pending
  then first final is legitimate, matching final redelivery is a duplicate,
  contradictory final is a conflict, and stale H1 cannot decide H2.
- Cases: success; early success; pending/unknown then success; H1 failure then
  H2 success (including duplicate/conflicting/stale controls); two failures
  reaching the cap; controller Stop while H1 waits; backend death while H1
  waits. Preserve raw ingress and node journal lines before deriving results.
- Stop uses the controller's explicit endpoint to cancel the one existing
  `arun` task and records cancellation propagation at the wait node. Deliver
  a failure after the graph has acknowledged interrupted state. It must not
  reach agent 2. This checks controller Stop, not the Langflow UI button.
- Backend death uses `docker kill --signal KILL` on the exact disposable
  labelled container. Start that same container once; its startup sweep marks
  the saved running case crashed and never calls `arun` for it. Deliver a
  matching failure after restart and observe for 1 second. No old graph or
  corrective invocation may resume. This checks process-fate behavior and
  the integration's terminal sweep, not Langflow checkpoint persistence.

## Source and execution boundary

The candidate code, graph construction and checks must be committed before
pre-run review. Record their exact SHA in a pre-run record. Freeze a fresh S1
case family before execution; each case is dispatched once. If setup fails,
save it and make a new committed amendment/identity before another attempt.
The original zero-model/zero-provider-write scope and no ambiguous-delivery
retry rule still apply. Do not run before independent pre-run approval.
