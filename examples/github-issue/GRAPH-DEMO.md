# Saved Langflow issue-operation demonstration

This example replaces the earlier CLI-only demonstration with an inspectable
Langflow graph: two live Issue Task outputs -> native Prompt Template -> pinned Skill
and native Codex Agent -> Output Contract -> Operation Data -> native GitHub Issue update -> confirmed-success condition -> native GitHub Issue close.
Failure, rejection and recovery route to separate read-only review destinations.
Run the final GitHub Issue close-target component to build the entire upstream chain. Running only
an Issue reader does not run the agent or cause a write.

The native Prompt Template composes issue text and instructions. The operation extraction adapter does not modify GitHub.
Extraction emits the agent-proposed changes with host-bound opaque grant and
stable request references. Both write vertices are the existing native GitHub
Issue class, with incoming Issue Reference and Operation ports. Its implementation
is unchanged; its existing HTTP client is embedded with a fixed local demo
backend address so the current viewer's global read-only connection is preserved.
The confirmed-update condition only emits the close Operation Data after the
update Issue node reports succeeded. The host checks its own receipt as well.
The host fetches the native record itself, checks native trace closure and the
exact requirements revision, and compares the proposal to the owner-approved
operation payloads before issuing a 60-second private issue grant. The operation-authorize endpoint cannot perform a GitHub write; only the native Issue execute requests can. It also checks
both original issue digests before the first mutation. The close API checks the
host's persisted update receipt, not merely the Data supplied by the graph.

The graph never contains a GitHub token or write capability. Local transport
uses the existing backend token file; provider credentials stay on the host.
The runner reuses the existing Codex subscription volume with unchanged command
permissions and a fresh explicitly capped campaign ledger (three turns for the corrected owner-approved follow-up). Same-user host processes
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

## Correction: native Operation-input verification

The original saved demo used effect helpers instead of the Issue Operation port.
That result is preserved as helper-based evidence, not native Issue-node
acceptance. The corrected exported graph contains 13 nodes and 15 connections.
The imported fake graph passed its actual editor Run component path through
both native GitHub Issue Operation inputs, with update then close. It used a
fake model and fake GitHub, zero native model turns and no real issue mutation.
The controller also rejects an altered operation or close without its own
confirmed update receipt, even if editable graph Data claims success.

The demo's writer nodes embed the standard backend client with this campaign's
local service address. Do not accept the catalog Update available action on
these nodes: that would restore the viewer's read-only global connection and
make the demo refuse writes. The Issue class and its Operation input handling
are unchanged. Some controller pre-dispatch refusals are conservatively shown
as unknown by the current client; inspect the host receipt rather than retry.
The corrected host suite passed 720 tests with 15 skips; 11 focused controller
tests passed. A fresh read after the fake editor saved the graph preserved all
15 logical edge handles and four AST-identical native Issue class definitions.
The fake mediation ledger records two confirmed effects and a revoked grant.

## Native prompt composition

Use the installed Prompt Template component for prompt composition. Connect
each GitHub Issue Task Message output to a named template variable, then Prompt
to Codex Task. The editor owns the wording and placement of each reference;
f-string-style placeholders require escaping literal JSON braces. This example
uses {update_issue} and {close_issue}. The Issue nodes are unchanged.

The host re-fetches both issues and compares their frozen digests before any
model turn is dispatched, and again before issuing a write grant. The frozen
rendered prompt must match at dispatch. Template editing in this bounded demo
does not authorize an arbitrary task or widen its approved operations. No
custom preparation component or /prepare endpoint is needed. Historical graph
and rejected-output evidence remain retained. This change does not loosen JSON
validation or alter retries, login, write targets or remaining turn allowance.
