# EXP-123: PR-head check feedback within one Langflow graph

Protocol draft for [Laomedo #123](https://github.com/amadou-6e/laomedo/issues/123).
Source base: Laomedo `develop` at
`a0ea0d8252841cde21647bdefc0a04d068b6b2fb`. Target contract:
[specs #297](https://github.com/amadou-6e/specs/pull/297) at
`7ee646f0531dc297444df79b7cdfc46a7e9f3700` (draft, **not merged**).
Before execution, pin the exact probe/component commit and the cached
Langflow 1.12.3 image
`langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0`.
An unavailable image, incompatible component API, or missing independent
pre-run review stops this experiment before any case is dispatched.

## Question and falsifiers

Can pinned Langflow hold one live graph at a PR-head gate, accept a later
external check observation for that graph, and route a matching failed check
to a **new bounded** agent-node invocation? A webhook that merely starts a
second flow is not a pass. A pass is falsified by any second graph run,
unmatched/stale/duplicate event causing an invocation, a failure loop beyond
the cap, uncorrelated trace IDs, or a backend restart resuming the old graph.
If Langflow cannot wait for external input without blocking beyond the
configured deadline, record that as a negative capability result. Do not
replace the test with application-side scheduling and call it native Langflow
support.

## Boundary and frozen cases

Use a disposable local Langflow container/volume and loopback-only fake
GitHub ingress. The ingress is a synthetic source with fixed repository,
PR number, head SHA, check ID, delivery ID and signed payload fixture; it
must not contact GitHub. An agent node is a deterministic counter that
returns a synthetic PR head. No model, Codex/Claude session, agent container,
GitHub token, provider write or real PR is used. Persist raw sanitized
request/response and graph-event records before deriving the summary. Cases
run under a fixed wall-clock wait deadline and a maximum of two agent
invocations per graph. Use fresh run, gate and event identities per case.

1. **Success:** first synthetic agent invocation returns head H1; deliver a
   matching passing check. Expect one graph run, one agent invocation and a
   completed gate.
2. **Failure then success:** H1 fails; expect exactly one new invocation
   returning H2. H1's later pass must not decide H2. H2's pass completes the
   same graph run, with two distinct invocation IDs and two visible waits.
3. **Duplicate, stale and conflict controls:** redeliver one delivery ID,
   deliver a result for a different PR/head, and deliver a contradictory
   status under the same check identity. None may dispatch another agent;
   the conflict must be visible rather than overwritten as success.
4. **Loop cap and Stop:** fail H1, then H2. The configured two-invocation cap
   must terminate visibly without H3. In a separate fresh synthetic graph,
   accept Stop while its gate waits, then deliver a matching failure. No
   post-Stop invocation may start.
5. **Backend death:** kill the disposable Langflow backend while a gate is
   waiting. After restart, a matching event must not resume that graph. Any
   later reaction is a separate run with a separate identity, not this case.

Run each dispatched case once. If a start or event delivery has an uncertain
result, inspect saved records and do not automatically redeliver with a new
identity. Any protocol amendment or retry must be committed before its new
case, with the previous observation retained.

## Required evidence and interpretation

Record image digest, component/probe commit, flow JSON/component-code hash,
graph run and invocation IDs, gate ID, repository/PR/head/check/delivery
identities, accepted/rejected event reasons, dispatch counts, loop counter,
terminal state, monotonic and UTC timestamps, and any post-Stop or post-crash
activity. Commit sanitized machine-written observations and hashes; keep
tokens, volume and raw private logs out of Git. The fake ingress proves only
local routing/correlation, not GitHub webhook authentication or delivery
reliability. Do not infer that Langflow owns durable ingress or that a failed
job had no side effects. If the native graph gate fails, report the missing
capability and design a reviewed adapter; do not silently promote a new-run
webhook into an in-run feedback mechanism.

Budget: zero model turns, zero provider writes. No live #104 identity is
reused or consumed. This protocol is not approval to run before the source,
image, component and independent review are frozen.
