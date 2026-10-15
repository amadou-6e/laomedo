# Historical agent activity prototype

The original prototype at `aee7d1c` inspected a separate PR-specific CLI adapter.
The user requested the existing `LaomedoCodexAgent`, so that adapter and its
toolbar coupling have been removed from the product path. No new agent node is
part of the intended architecture. The retained API/store and modal source are
unwired preparatory code, not a completed observability feature.

See the [real feasibility study](../experiments/feasibility/agent-observability/README.md)
for the available native/OTLP signals and original Docker-runner blocker.
The target is a graph-wide Agents tab with multiple turns, tool/message details,
subagent hierarchy and token/cost series, not a one-node transcript modal.

Set `LAOMEDO_AGENT_ACTIVITY_DB` on the Langflow host to a private SQLite database
outside the checkout. Only the host chooses this path. Capture reserves the
authenticated user, flow and node identities before dispatch. If reservation
fails, the configured capture path refuses to start the agent. Existing runs
without capture have no retained activity; an empty history does not mean zero
agent actions. Reading requires the same signed-in owner.

The native agent commits each parsed JSON event before deriving the display.
Cancellation/failure retains committed receipts and marks the capture partial.
A clean native terminal event and process exit close the local stream; they do
not prove task success. Unknown usage remains unknown, and measured zero is
displayed as zero. Native event bodies can contain sensitive task content:
protect the database with the same private host permissions as the Langflow
state. There is no public export or automatic expiry.

Historical saved graphs embed the removed adapter's component source. They must
not be reimported as the current Agent. The retained store cannot reconstruct
events from older turns whose temporary event files have already been removed.

The API is under `/api/v1/laomedo/agent-activity/{flow}/{node}`. The invocation
endpoint adds `/{invocation}?after=0&limit=100` (maximum 200). It never calls the
agent or a provider. No database filesystem path comes from the browser.

The old prototype supported `NativePRAgent` only. Docker-runner event integration, Claude,
cross-agent overview, deletion UI and hard-crash durability acceptance remain
unfinished. The existing RunnerTraceBridge and WorkflowRunStore keep their
separate runner correlation responsibilities; this viewer does not replace or
silently merge those records.
