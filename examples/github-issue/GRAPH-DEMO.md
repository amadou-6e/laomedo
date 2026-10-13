# Saved Langflow issue-operation demonstration

This example replaces the earlier CLI-only demonstration with an inspectable
Langflow graph: two live Issue selections -> task preparation -> pinned Skill
and native Codex Agent -> Output Contract -> host-mediated update -> close.
Failure, rejection and recovery route to separate read-only review destinations.
Run the final Close component to build the entire upstream chain. Running only
an Issue reader does not run the agent or cause a write.

The three small graph-components are demo adapters, not new general-purpose
GitHub write components. Their fixed host endpoint accepts only the frozen
campaign, exact native proposal and selected two issues. Existing GitHub Issue
readers, Skill, Codex and Output Contract implementations remain unchanged.
The host fetches the native record itself, checks native trace closure and the
exact requirements revision, and compares the proposal to the owner-approved
operation payloads before issuing a 60-second private issue grant. It also checks
both original issue digests before the first mutation. The close API checks the
host's persisted update receipt, not merely the Data supplied by the graph.

The graph never contains a GitHub token or write capability. Local transport
uses the existing backend token file; provider credentials stay on the host.
The runner reuses the existing Codex subscription volume with unchanged command
permissions and a fresh four-turn campaign ledger. Same-user host processes
remain trusted. This does not claim a protected human approval boundary.

Export using build_graph_demo.py --config <private-config> --output <local-json>.
Configuration/API/compiler access and activation are separately approved. The
prepare_graph_demo.py creates only the two explicitly approved disposable
fixtures, records each create intent before dispatch and refuses uncertain
creation rather than retrying. Never reset a campaign, old ledger or grant.

Use a separate fake graph for browser verification. The fake runner and fake
GitHub service spend zero model turns and never mutate a real issue. Reserve
the live campaign's first Run for the owner. After publication has begun, the
preparation and runner refuse another new invocation. Stable effect identities
permit receipt reconciliation without repeating an unknown or completed write.
The grant is revoked after close or any failed/uncertain mutation, and expires
if the graph stops between update and close. No push or PR is authorized.

Limitations: the graph-specific helpers currently have a fixed local demo
endpoint, platform paths and frozen exact targets; they are not a reusable
arbitrary issue-operation workflow. Output Contract acceptance alone does not
authorize a write; the independent host-native check must also pass. A native
live run through this imported graph is unproven until the owner executes it.

If the graph pauses for more than the 60-second grant between update and close,
close is refused. That leaves a confirmed update and an open close target;
there is no silent grant renewal or repeated write. Inspect the saved receipts
and request a separately approved recovery if needed.

## Verification, 2026-10-13

The host suite passed 717 tests with 15 skips before the final handle regression
was added; the final focused suite passed 9/9. The actual imported fake graph's
Run component path completed update then close, with two confirmed effects and
one revoked grant. A fresh API read after editor opening/saving retained all
ten logical edge handles, including the Message task port. The owned temporary
flow and fake-service process were removed. This uses a fake model and fake
GitHub, zero native model turns and no real issue mutation.

Recovered verification defects: the initial task handle used type other instead
of the native str type and was removed by the editor; the first encoded handle
correction was damaged by shell Unicode conversion, caught before execution.
The export now takes target types from compiled templates and emits the native
quote separator with a numeric code point. The fake runner initially omitted
client_request_id, correctly producing recovery and no issue effects; the fake
response was corrected to the actual runner protocol. Those refusals remain in
the ignored verification records and did not consume live allowance.
