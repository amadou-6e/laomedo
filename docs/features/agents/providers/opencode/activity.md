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
USD estimate charts. The Gantt and breadcrumbs select the invocation, conversation or turn; the
cards and both charts follow that same selection. Hover or focus a chart and use Left/Right, Home or End
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
Task delegation**. That historical harness disabled native Task invocation.

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


## Merge preparation, 2026-10-25

A subsequent real Run component invocation completed one native parent Task and
one read-only child in the saved local graph (execution
`383a237d-45c2-4da3-92e3-5a1ef1b86efb`). Parent and child turns were 58.4s and
27.5s; the 138.3s invocation receipt range also includes idle/startup/cleanup.
The complete stream and owned-controller cleanup were confirmed. This later run
establishes agent Task delegation separately from the earlier host-created child.

A trusted host-only configuration hook now permits an additive named-agent policy
without replacing normal skill/worker tools or the primary prompt. The local
profile's child has no tools or further delegation. The real run above preceded
the final restoration of those normal defaults: startup/configuration tests are
current evidence, while another paid run of restored tool paths is not claimed.

Normal runners use `attempt-count.json` for a diagnostic sequence and do not read
historical experiment turn allowances as runtime authorization. Bounded examples
and internal controls explicitly use `experiments/turn_harness.py`; those bounds
are not installed in normal startup or persistent services.

Initial running total cards show zero only before any usage observations and
without capture warnings or truncation. Subsequent missing/unpriced fields and
completed captures with no usage remain Unknown. The initial zero is provisional,
not a measured provider charge. Internal tests cover the transition; no additional
paid run was submitted solely to verify these cards.

The implementation is stacked on the shared descriptive-error presenter. Its
producer-specific catalogue guard scans literal raises and capture/error fields
in the OpenCode boundary, runner, native reader, telemetry exporter and activity
observer. It does not claim exhaustive coverage of arbitrary external exceptions;
those use the safe fallback. Capture explanations retain safe machine codes in
the shared details control, without raw exception bodies.

## ACP child capture and export deadlines

ACP streams the root conversation. After controller cleanup, credential-free,
network-disabled native CLI exports provide child ancestry, tool identities and
per-conversation usage. Child activity is available after export, not as a live
child stream. Repeated snapshots and ACP usage must not be counted twice.

The whole export tree has an approximate 120-second default budget, including CLI
startup and Docker cleanup; stream termination and cleanup waits can overrun it
by about ten seconds. Each individual export remains limited to 30 seconds. Trusted
host configuration may set `LAOMEDO_OPENCODE_HISTORY_EXPORT_SECONDS` from 45 to
600 seconds; a lower value can leave a multi-session capture incomplete. This is
a metadata deadline, not a model-turn allowance. Timeout does not retry a prompt
or claim that missing usage is zero.

On 2026-10-29, revision `4eb5d95` ran one explicitly authorized native Task child
through ACP. The child received actual documentation text and had no tools or
further delegation. A verification-only standard ACP allow-once response consumed
that authorization; the product client still denies permission requests by default.
The original graph completed but native capture was marked partial. Its failure
cause was not instrumented and remains unconfirmed.
The same genuine parent/child exports were later read and projected offline with
no additional model calls, confirming exactly one parent-linked child and separate
usage. That offline export took 11.64 seconds and would also have fit within the
old 45-second budget. The larger budget is a robustness improvement, not evidence
that it fixes the original failure. This reconciliation is not a successful
original live capture or proof of production delegation controls. End-to-end
capture requires a separately authorized new child run with export diagnostics.

The Agent node waits 210 seconds by default, with a 240-second maximum. OpenCode
can need startup, a 180-second prompt and final export; Resume also needs a baseline
export. These phases can exceed the node's wait, and cancellation can still be
followed by metadata capture. A wait timeout therefore leaves the run outcome
unconfirmed. Retain its reference and inspect existing work before dispatching
again; a longer metadata budget does not extend the node's wait or retry a prompt.
