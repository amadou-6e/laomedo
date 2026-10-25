# OpenCode Activity capture

OpenCode uses the existing graph-wide Activity page, timeline and conversation
renderer. Inspecting Activity never submits a model request.

Each accepted fresh/resume attempt has independent native and OTLP receipt
boundaries. The adapter subscribes to native SSE before sending the prompt,
filters other sessions and previous messages, then reconciles HTTP completion
snapshots by native message/part identity. This avoids charging snapshots and
live updates as separate requests. Capture failures do not change task success.
A missing root terminal, missed child coverage or capture failure marks the
stream incomplete. Repeated raw receipts remain inspectable.

Messages, command/tool inputs, outputs and native metadata come from actual
OpenCode records. Native parentID links identify children; text claiming to have
spawned another agent is not a parent link. Children without complete usage
make inclusive totals unknown rather than silently reporting zero.

Token categories preserve fresh input, cache reads, cache writes, output and
reasoning. Normalized input includes both cache categories; output includes
reasoning. Per-request runtime catalog rates, cache-write prices and context
tiers produce API-equivalent USD estimates. These are not subscription charges
or invoices. Unsupported/missing usage or prices remain unknown. Cumulative
usage/cost points are attributed to their native thread and effective model.

Install the `observability` optional dependencies and set
`LAOMEDO_RUNNER_OTEL=1` on the runner to emit OTLP spans into its local receiver.
These spans are explicitly labelled **adapter-observed** and derive from native
receipts; they are not claimed to be OpenCode's own SDK instrumentation. Span
attributes carry identity, timing, tool name and session-level usage, without
prompt or tool-argument text. Raw Activity receipts retain the conversation.

## Usage and record inspection

The selected invocation shows run-total cards and separate cumulative token and
USD estimate charts. Chart scope selects all observed threads or one native
thread without changing the run-total cards. Hover or focus a chart and use Left/Right, Home or End
to inspect captured observations. Latest cumulative values are carried forward
per thread before aggregation; missing categories remain gaps.

OpenTelemetry records are listed without a frontend record-count cutoff.
Fuzzy search covers names and JSON metadata; Clear restores every loaded record.
Individual JSON payloads stay collapsed until opened. If the host detail limit
is reached, the existing partial-view warning remains visible.

## Live verification, 2026-10-23

A real Docker-backed OpenCode Go/gpt-6-luna resume through Run component captured
62 new receipts and five OTLP spans. Its isolated usage was 1,803 input and 45
output tokens, estimated at $0.0002478.

A separate fresh graph run loaded the pinned skill and executed the approved
`head -n 6 README.md` command. Activity displayed both tools, exit status, output,
final reply, three cumulative usage points and seven OTLP spans. Total usage was
4,008 input (including 2,521 cached), 107 output; estimate $0.00026436.

One separately authorized, host-created native child used only the approved
README excerpt, with tools denied. Native parent linkage, separate usage and
cost, and adapter OTLP export were verified against genuine parent/child records.
The harness's README text contained a misdecoded arrow; this affected the test
input, not the capture or attribution. The child's usage was 1,100 input and 150 output (including 114 reasoning),
estimated at $0.000212425. This verifies native child observation, **not agent
Task delegation**. The dedicated runner still disables native Task invocation.

Three additional prompt submissions were used out of the five authorized.
Both graph runs and the child controller confirmed cleanup. Internal fixture
checks complement these observations; they are not live acceptance. The feature
remains unmerged pending the user's working graph review.

The screenshots and browser checks cover the real fresh-run Activity page and
conversation, not a child-thread view. Live cancellation was not exercised in
this bounded observability verification. Native receipts can include opaque
provider-encrypted reasoning blobs; these are retained with the original record,
not decrypted or treated as readable reasoning.


### Conversation navigation

The Gantt is the scope selector. An invocation row shows all captured conversations;
conversation rows show only their own turns (excluding descendants), and turn rows
show only the selected turn. Native session titles label child conversations when
observed; otherwise the UI uses a neutral numbered label. Titles do not attest who
started a child. The saved host-child demonstration retains its observed
`Host-started read-only PR workflow summary` title.

Breadcrumbs restore ancestor conversations or All activity. Messages, telemetry,
usage cards and charts follow the same scope. Telemetry is included only when its
conversation and turn/call IDs explicitly match; unlinked records remain visible
in All activity. Conversation totals use provider-attributed per-thread usage;
turn totals require explicit per-turn counters. OpenCode counters sum native
assistant responses within that turn; Codex subtracts cumulative counters recorded at an explicitly identified
turn start from subsequent cumulative updates for that native turn ID. Without a
recorded starting baseline, per-turn usage stays Unknown. `tokenUsage.last` is
not used as a whole-turn total. Missing attribution stays Unknown. Truncated or boundary-unverified
captures cannot recover withheld totals through a narrower selection.

Earlier-run navigation appears only for an earlier non-overlapping invocation of
the same node/provider/native session within the current graph. It navigates to
recorded evidence; it does not dispatch Resume or claim that missing history was
captured. The Gantt and breadcrumbs replace the raw thread-links disclosure; no additional
technical-details disclosure is added. The existing Node identity control is retained.


The graph timeline uses one row per captured agent conversation within an invocation.
The main row uses the recorded graph node name; child rows use observed titles.
Turns are clickable intervals on those rows, never separate rows. Only positive,
valid captured turn intervals are drawn, clipped to the existing graph-execution
axis. There is no green invocation-duration or conversation-envelope bar bridging
startup, cleanup or idle gaps. The axis still uses invocation receipt start/end
boundaries. Row labels select the conversation, segments select their native turn,
and All activity restores invocation-wide evidence.

Conversation search matches messages and tool records without reordering the
transcript. Changing the selected run, conversation or turn clears its search.
Conversation exports are available as Markdown or JSON; OpenTelemetry exports
are JSON records, not an OTLP ingestion envelope. Both exports use the currently
selected scope and active search filter, and include that context in the file.
Conversation JSON retains captured message/tool metadata; Markdown includes
message text and fenced tool metadata. Capture state and partial-capture flags
remain in the export. Downloads are local and do not dispatch agents.

Persistent explanatory paragraphs are removed from the activity page. Cost
estimate provenance, token accounting notes and telemetry coverage remain
available through the section info controls. Capture warnings and empty states
remain visible.
