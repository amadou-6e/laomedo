# Historical agent activity prototype

The prototype at `aee7d1c` inspected a separate PR-specific CLI adapter. The user
requested the existing `LaomedoCodexAgent`, and explicitly selected removal of
the PR-specific agent on 2026-10-15. That component, its live graph builder/export
and toolbar coupling have been removed from the product. The retained read-only
API remains mounted, but has no producer; the modal has no toolbar entry. These
are preparatory code, not a completed original-agent product feature.

See the [real feasibility study](../experiments/feasibility/agent-observability/README.md).
The target is a graph-wide Agents tab with multiple turns, tool/message details,
subagent hierarchy and token/cost series. No replacement agent node is needed.

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

Historical saved graphs embed the removed adapter's component source. Do not
reimport those as the current Agent. The retained store cannot reconstruct older
events whose temporary files have already been removed.

The API is under `/api/v1/laomedo/agent-activity/{flow}/{node}`. The invocation
endpoint adds `/{invocation}?after=0&limit=100` (maximum 200). It never calls the
agent or a provider. No database filesystem path comes from the browser.

The historical prototype supported `NativePRAgent` only. Docker-runner integration, Claude,
cross-agent overview, deletion UI and hard-crash durability acceptance remain
unfinished. The existing RunnerTraceBridge and WorkflowRunStore keep their
separate runner correlation responsibilities; this viewer does not replace or
silently merge those records.
