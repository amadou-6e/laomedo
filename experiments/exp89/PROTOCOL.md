# EXP-89: UI Stop propagation to the native runner

Issue: https://github.com/amadou-6e/laomedo/issues/89. Source base:
Laomedo `f7a83f085d38caadc1e19838da09eb44c2d7a1df` (`develop`).
Governing specs: `amadou-6e/specs` `b9038e976f8c06f3479193bf515a490cca494b5e`,
Langflow integration Q11 and agent-execution cancellation contract.
Runtime: cached Langflow 1.12.3 image
`langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0`.

## Question and falsifiers

When the operator presses **Stop** in Langflow's graph-run UI, does the
Langflow 1.12.3 backend signal the active Laomedo Codex component, and does
that component actually issue a native runner cancellation? The current
component shields its blocking HTTP task; do not assume the graph's stopped
status means the agent stopped. A claimed propagation pass is falsified by
zero runner cancel requests, a late synthetic effect, or inability to link
the clicked UI run to the runner request. UI Stop after terminal completion
is a negative control and must not be counted as active cancellation.

## Frozen environment and cases

Use one disposable Langflow container and volume, localhost-only published
port 7864, `LANGFLOW_AUTO_LOGIN=true`, with the committed Codex component
mounted read-only. Use a synthetic loopback-only runner reachable through
`host.docker.internal`, authenticated with a synthetic token file; no Codex
login, model call, real agent container, GitHub write or production data.
Use a browser click on the visible Stop control, not merely a direct backend
API call. A headless local browser is acceptable if it records the clicked
control and resulting requests. Pin the browser/probe revision before running.

Case A: freeze a graph that starts one synthetic run but holds its early
acknowledgement for 3 seconds. Click Stop after the runner records exactly
one POST and before the acknowledgement returns. Observe for 8 seconds.
Case B: freeze the same graph with immediate acknowledgement and a synthetic
tool wait of 6 seconds. Click Stop after the runner records the wait start.
Observe for 8 seconds. Negative control: let one synthetic run complete,
then press Stop and verify no new cancellation is credited to the completed
run. Each case is run once; no retry of an uncertain start.

Record sanitized monotonic/UTC timestamps for UI click, browser request,
Langflow job state, component cancellation hook, runner POST/GET/cancel counts,
runner run ID, terminal runner status, and any synthetic effect. A missing
observation is `unknown`, not `false`. Preserve raw enough local logs to audit
event ordering, but publish only IDs, status and count/timing summaries with
no token or task text. The total active window per case is at most 12 seconds.

## Interpretation

UI Stop reaches the runner only if the same native run receives a cancel
request after the click and before its synthetic wait completes. A runner
cancel acknowledgement is not proof of native model stop; this probe has no
real model. If the browser control or backend hook cannot be driven in the
pinned environment, report feasibility failure without substituting an API
Stop call as UI evidence. This probe does not test queued-stage Stop races
(#41), real-agent timeouts, or runner-crash cleanup. Model-turn budget: zero.
Any case amendment must be committed before the amended run.
