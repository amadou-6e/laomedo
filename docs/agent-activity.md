# Graph agent activity

The **Agents** section in the graph sidebar shows retained activity from the
original `LaomedoCodexAgent`. The singular Agent section retains its A2A setup.
There is no PR-specific agent.

Choose a graph execution to compare invocation and turn intervals, including
explicitly linked child turns. Select an invocation for messages, highlighted
JSON tool details, token counts, API-equivalent estimates over time, and retained
OpenTelemetry records. Times are local, with UTC tooltips. Bars use runner receipt
times. Viewing and polling never dispatch agent work.

## Host configuration

Set `LAOMEDO_AGENT_ACTIVITY_DB` on the Langflow host to a private SQLite path
outside the checkout. Capture reserves the authenticated owner, persisted flow,
graph execution and node before dispatch. A configured reservation or runner-auth
failure refuses dispatch. Leave capture unset for legacy behavior.
`LAOMEDO_RUNNER_TOKEN_FILE` selects the runner's existing host API token; the join
bridge has a separate credential. No token goes into the graph or browser.
Multiple trusted local test runners can share a dedicated test API token.

Install `laomedo[observability]` on the runner host and set
`LAOMEDO_RUNNER_OTEL=1` for per-launch local OTLP logs/traces collection. The
loopback receiver uses an ephemeral launch bearer, bounded protobuf requests,
and an attribute allowlist for correlation, model, timing and usage. Account and
email identifiers, prompts and arbitrary log bodies are excluded. Native events
supply task messages and tool contents. Docker must reach the receiver through
`host.docker.internal`; this was checked on Docker Desktop.

`LAOMEDO_RUNNER_MULTI_AGENT=1` separately enables at most two native threads and
depth one, with automatic memories disabled for that process. The existing turn
ledger counts top-level submitted turns, **not every child model request**; this
setting is not a monetary budget enforcement mechanism.

Historical graphs embedding the removed PR adapter must not be reimported as
the original Agent. Missing old events cannot be reconstructed.

Saved graphs embed source: update the original Codex node for capture. Prior Run
is visible so saved resume edges survive opening the graph. Existing Docker
image, CLI version and sandbox checks still apply.

## Identity and evidence

Binding follows the original request-identity validation. Source cursors dedupe
network retries, while distinct repeated/conflicting native receipts remain
retained. Native thread/item IDs drive the projection. Explicit child links
define agent membership; overlapping internal spans never imply subagents.
Each accepted runner attempt has a unique identity and records durable native/OTLP
source boundaries after streams close. The observer reads only that exact attempt;
busy/refused dispatches receive no native receipts or attributed usage. Repeated
references to an already captured attempt do not count its usage again. Resume
baselines come from the runner's accepted-attempt record before the model turn,
not a caller's earlier snapshot. Later resumes cannot enter previous invocations. Updates are differenced,
never summed; regressing counters and missing usage remain unknown.

### Codex parity with the shared Activity view

Codex and OpenCode use the same agent rows, turn segments, usage charts,
OpenTelemetry search/export and final scrollable Conversation section. Codex
native agent-message and command-output deltas update provisional items while
running; the completed item is authoritative, including after late deltas.
Native MCP and dynamic tools keep their readable names and expandable metadata.

A newly accepted Codex `thread/start` attempt records `fresh_thread: true`.
The observer retains that runner attestation with its usage baseline, allowing
the first turn to use a proven zero boundary. Resume uses the previous native
cumulative snapshot. Neither an empty history nor `tokenUsage.last` proves a
whole-turn total; the latter can describe only the last model request. Older
captures without a proven boundary retain unknown first-turn totals.

Native `subAgentActivity` creation supplies the child's thread relationship,
path/name and first usage boundary when received before its first turn.
Replayed or late creation receipts cannot reset an observed boundary. Child
models still require their own runtime evidence. No prompt text or overlapping
span is accepted as proof that a child exists.

Explicit OTLP thread/turn/call aliases are normalized for scope selection.
Conflicting native identifiers remain visible in All activity and its export,
but are excluded from narrower scopes and model attribution. Raw receipts are
unchanged. These transformations do not attest exporter flush completeness.

A captured native terminal event closes native stream evidence, not task success.
OTLP exporter flush completeness remains unverified and is labeled separately.
Failures and cancellation retain partial evidence. A hard app crash can leave a
capture marked running; automatic recovery and retention/deletion policies remain
unimplemented. Existing RunnerTraceBridge and WorkflowRunStore stay independent.

## Cost

The catalog records Standard USD API rates for `gpt-6-luna` and `gpt-6.1-sol`,
checked on 2026-10-15. Estimates subtract cached input from input and charge
output once; reasoning tokens are not added again. The UI states the Standard,
no-regional-premium assumption and excludes tool fees. These estimates are not
actual subscription charges or account-credit consumption.

Unknown models/categories, nonzero cache-write overlap, counter regressions,
and totals above the long-context threshold remain unpriced. Child estimates
require independently observed child model metadata and usage. Native and OTLP
usage observations are never added together.
OTLP child-model attribution is runtime-reported, not independently attested.
The configured sandbox denies tool network access; enabling a different network
profile would need a separate trust assessment. Truncated detail views suppress
usage and cost totals rather than reporting a partial snapshot as a full total.

Sources: [Luna pricing](https://developers.openai.com/api/docs/models/gpt-6-luna),
[Sol pricing](https://developers.openai.com/api/docs/models/gpt-6.1-sol).

## Read API

All browser routes require the signed-in owner and return `Cache-Control:
no-store`. GET opens SQLite read-only/query-only and never creates files.

- `/api/v1/laomedo/agent-executions/{flow}?execution={graph-run-id}` returns up to
  500 invocation summaries, newest first.
- `/api/v1/laomedo/agent-executions/{flow}/{node}/{invocation}` returns the
  projection and at most 20,000 receipts, with explicit truncation.
- Legacy `/api/v1/laomedo/agent-activity/{flow}/{node}` and
  `/{invocation}?after=0&limit=100` remain (maximum page 200).
- The separately authenticated host runner's `/v1/runs/{run}/events` supplies
  bounded native notification/OTLP pages. Account RPC responses and arbitrary
  filesystem paths are not exposed.

Protect the database like private Langflow state: native messages and tool
outputs contain task content.

## Validation scope

Internal tests cover owner/execution isolation, read-only inspection, source
pagination, retry deduplication, conflicting receipts, resume baselines, counter
regressions, pricing unknowns and invocation boundaries. They are not real
integration acceptance.

Real verification uses the original Docker CLI 0.159.2 on the reviewed rebuilt
image, real README reads, concurrent runners and a resumed thread. Exact graph
executions and source revisions are recorded separately. Other providers, OTLP
metrics, historical-image parity, hard-crash recovery and cross-machine collector
setups remain outside this verified implementation.

The real [competing-resume check](../examples/agent-activity/resume-contention-evidence.json)
adds the adversarial case: two original nodes target one completed run, one resume
is accepted and the refused node has zero events/turns and unassigned usage/cost.
The source hashes identify the tested controller mechanism. This is separate from
the positive concurrent/subagent example and from internal fixture tests.
