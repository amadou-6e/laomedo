# EXP-10 prospective long-call timeout protocol

Issue: https://github.com/amadou-6e/laomedo/issues/40
Source base: Laomedo `a36523845a1e718fb79fb40d42002a03c0cb4861` (`develop`).
Governing draft: specs `447c4d5044a5b33f59420c1f95ec103979ad5abf`,
`projects/laomedo/subsystems/langflow-integration/design/decision-readiness.md` Q11/E03.
Runtime: pinned Langflow 1.12.3 image
`sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0`.

## Question and falsifiers

When a long synchronous Langflow agent-node call exceeds the outer client's,
the component's, or the server's configured timeout, which layer terminates,
which effect continues, and what evidence remains? A timeout response alone
must never be treated as proof that a remote action stopped. Fail a claimed
safe timeout if a late effect is omitted, a later success is reported as timely
completion, or a running side effect is asserted cancelled without evidence.

## Frozen cases and limits

Use a disposable Langflow container, a synthetic HTTP runner **inside the same
container**, a localhost-only published Langflow port, and a temporary named
volume. The runner records request entry and a durable synthetic effect after
its delay; it makes no model, GitHub or external service call. The graph is
the pinned native Codex component with a synthetic skill reference and token.

1. Control: endpoint delay 0.2 seconds, component timeout 8 seconds, outer
   client timeout 15 seconds. Expect one effect and a successful response.
2. Outer client: endpoint delay 4 seconds, component timeout 8 seconds,
   caller timeout 1 second. Inspect both the immediate client error and the
   endpoint/effect after 5 seconds; do not assume disconnect cancelled graph.
3. Component HTTP: endpoint delay 5 seconds, component timeout 2 seconds,
   caller timeout 15 seconds. Inspect the Langflow response/error, then the
   endpoint/effect after 6 seconds. No early success may be reported.
4. Langflow server: set and verify `LANGFLOW_WORKFLOW_EXECUTION_TIMEOUT=3`,
   use the v2 synchronous workflow route, endpoint delay 6 seconds,
   component timeout 8 seconds, caller timeout 15 seconds. Inspect HTTP
   status/body, job/trace status if exposed, and the endpoint/effect after
   7 seconds. The v2 server ceiling must not be confused with the v1 route.

Record actual monotonic durations, UTC timestamps, response category, runner
request/effect counts, stage/run IDs when available, container/process state,
and whether a later effect occurred. Sanitize the observation: no token or
auto-login URL. Stop after one attempt per case; do not retry a potentially
active call. Max four synthetic calls, zero model turns, one disposable
container and named volume. Client waits are bounded to 15 seconds; endpoint
delays are at most 6 seconds. If a route fails validation before dispatch,
record that as inconclusive for its timeout claim rather than changing cases
silently. Keep the initial frozen protocol unchanged; amendments are explicit.

This probe establishes only behavior at the pinned versions and configured
timeouts. It does not test a real Codex process, external cancellation, power
loss, or unattended approval handling. Product acceptance still requires an
effect-aware run/trace integration, not just this runtime observation.
