# Current Claude Code Docker templates

Use [flow.json](flow.json) for Skill -> Claude -> Skill Operation, or
[current-template-flow.json](current-template-flow.json) for a fresh Agent with
optional skills. Both embed the current component, inherit the current Codex
ports (without a Handoff input), discover native model/effort options, and expose Execution Timeout under
Advanced controls. Configure the dedicated local runner as described in
[the Docker guide](../../docker/claude/README.md).

Normal runners have no verification-only global turn ceiling. The records and
allowances below describe separate historical campaigns, not current startup
configuration or authorization for future normal runs.

The following executed exports are immutable historical evidence, **not current
runnable templates**: `activity-flow.json`, `executed-flow.json`,
`first-executed-flow.json`, and `no-skill-flow.json`. Their embedded components
and original campaign proofs are deliberately preserved. Use the two current
templates above for new work.

## Historical campaign documentation

# Claude Code Agent

The Claude node uses a dedicated Docker controller and Claude Code subscription
login. Its Agent ports, output validation, same-session corrections, handoffs,
selected artifacts and activity records share the Codex orchestration contracts.
Skills are optional. Fresh creates a private writable draft; Resume binds the
same native session to its exact completed snapshot, account, image and grants.
A compatible API restart does not invalidate that binding.

Build and authenticate the dedicated image/profile as described in
[docker/claude](../../docker/claude/README.md). Start the independent lease
supervisor before the runner, using private state directories outside Git:

```powershell
python -m laomedo.host.leases.lease_service --help
python -m laomedo.agents.providers.claude_runner --state <private-state> --skill-store <registry> --source <source> --lease-service <supervisor-state> --port 8769
```

Set `LAOMEDO_CLAUDE_RUNNER_TOKEN_FILE` in the Langflow host to the runner's
private `api-token`. An optional Claude join bridge uses
`LAOMEDO_CLAUDE_BRIDGE_URL` and `LAOMEDO_CLAUDE_BRIDGE_TOKEN_FILE`; a Codex
bridge environment setting never redirects Claude. Exported graphs contain
neither API tokens nor subscription credentials.

Native controller file and shell tools are disabled. All draft file reads,
edits and commands execute in a network-free worker without the subscription
profile. External GitHub
operations require a host-authorized scoped mediation grant. Pinned native skills
are byte-preserved, read-only plugin bundles. Skill metadata that could override
permissions/model/session or execute controller-side preprocessing is refused
before dispatch. The chosen skill cannot widen the frozen controller grant.

Normal runners have no verification-only cumulative turn allowance. Execution
Timeout bounds one invocation including output corrections; the HTTP timeout is
separate. Cancellation is confirmed only after owned controller/worker cleanup
is verified. Unknown remote mediation outcomes require reconciliation, not a
blind retry. Requested effort and native-reported effort remain distinct; an
unreported native effort is unknown.

The current implementation uses the official CLI stream protocol, pinned to
2.1.310, rather than claiming SDK transport. Its profile is dedicated, with no
personal sessions copied. Local login-only migration requires explicit operator
authorization; this is a single-user subscription prototype, not a production
multi-user authentication design.

## Historical proposal-mode verification

The evidence below describes the earlier host adapter pinned to 2.1.301. It is
retained as history and does not establish Docker, restart, cleanup or tool
acceptance for the current implementation. Its experiment allowances are not
normal runner configuration.

## Recorded real verification

The actual native Langflow API executed Skill -> Claude -> the same Skill
Operation with a real subscription. The first run added the missing description,
with exact CRLF byte preservation, a parent-linked registry commit and backend
provenance. Its verifier mishandled newline comparison and stopped the runner
before resume; [first proof](first-skill-proof.json) preserves that successful
edit and the harness error.

Within the unchanged three-turn ceiling, a new explicit description revision
then succeeded, and one resume of its native session returned the identical
proposal. Exact byte readback, expected parent, unchanged source/canonical and
same-ticket replay without an extra commit/turn passed. The runner was stopped
and the preview's edit-policy map is empty. No correction was needed in these
real runs; correction mechanics are covered by internal controls only.

[Evidence](evidence.json), [executed flow](executed-flow.json),
[first executed flow](first-executed-flow.json), [read-only review flow](flow.json)
and [accepted bytes](generated-skill/SKILL.md) preserve the result. Scoped Git
attributes retain source/accepted CRLF bytes without text normalization.

The shared Agents view contains the real graph invocation and explicitly
adapter-normalized activity. Native CLI terminal receipts remain in private run
state. Parent exit was observed; complete SDK evidence, descendant cleanup and
unknown usage/cost metrics are not claimed. This verifies Skill operations, not
a live PR operation or writable coding-tool access. The future isolated SDK
mode remains separate.

When resuming a node configured with explicit output requirements, clear the
requirements input/JSON: the runner retains the original contract; changing a
contract on a resumed session is refused. Install the component category on the
runtime package search path as in the OpenCode adapter. The dedicated example
host adds `components/laomedo` to `laomedo.__path__` before component discovery.

## Real graph activity verification

On 2026-10-23 the user explicitly approved one additional, read-only Claude
summary turn to verify the new capture. The original three-turn campaign and
its ledger were preserved. A dedicated runner with a one-turn ceiling read the
pinned test skill through the actual Claude node in Langflow; no edits,
operations, correction or resume were requested. The runner is now stopped.

[Activity proof](activity-proof.json) and [executed graph](activity-flow.json)
record the tested source revision. Authenticated readback verified the exact
submitted prompt against its turn hash, the answer against the native receipt,
one completed timeline turn, the native-reported model, token counters and
terminal diagnostics. Input was 1,403 tokens (including 1,401 cache-write tokens),
output 98, cached reads and reported thinking both zero. The CLI's session cost
is a labelled estimate, separate from the unknown independently priced cost.
The source skill and older recorded runs were unchanged.

The initial verifier stopped on an inapplicable retry-setting assertion: without
an output contract the component does not send continuation settings, so the
runner retains its default. The completed receipt and failure were preserved;
remaining checks used read-only reconciliation, with no second dispatch. The
hard ledger remained one of one turns. This verifies fresh successful capture,
not new live correction, resume, cancellation, subagents or writable tool use.

## Current develop compatibility

The [current template export](current-template-flow.json) contains the node
inspected in the live preview, with the native model catalogue and shared
Advanced controls. It defaults to Status for the previously completed real run;
it requires that runner's retained state and does not grant a new model turn.
The [model discovery proof](model-discovery-proof.json) records the actual CLI
picker comparison, refresh, model/effort selection, reload, light/dark/narrow
views, and real pre-dispatch invalid-effort validation. Historical executed
exports above retain their original tested component source.

The current builder uses an independent read-only Skill node connected to the
Agent's Skill References input, matching current develop. The edit target still
connects Task and receives Operation feedback. Earlier executed two-node exports
retain their original tested source revisions; they are historical evidence,
not newly executed proofs of this updated builder. Claude now preserves Codex's
input order and dropdown/refresh widgets, uses the same hidden internal fields
and collapsed Advanced controls, and loads its choices from the Claude runner
with the Claude runner token. It never queries the Codex RPC model catalog.

The Claude selector now loads the native signed-in CLI model picker through an
initialization control request, including Default, current aliases, versioned
models, display names, resolved model IDs and each model's supported effort
levels. Nothing is hardcoded as an available model. Refresh sends no user
message, submits no model turn and disables session persistence. The native
catalogue is labelled `cli_reported`; it does not guarantee a subsequent turn
will succeed or bypass subscription limits.

Models that support effort expose the levels reported by the CLI, including
`xhigh` and `max` when available. Models without effort select `default`, and
execution omits `--effort`. Imported selections are preserved in the editor;
fresh/start validates the actual model/effort pair against current native
metadata before creating a run. A failed refresh reports the existing model-list
error and never falls back to an invented list. Discovery has an 45-second CLI
timeout plus a 15-second authentication check, below the Claude editor's 75-second
request timeout; concurrent refreshes cannot spawn overlapping catalogue CLIs.

The shared descriptive error presenter from PR #181 is included in this branch.
Claude runner failures have explicit catalogue entries and an additional
producer-specific coverage check, including named error codes. Model refresh
alerts show actionable recovery directly; graph failures retain the original
code under Technical details. Unknown failures use the shared safe fallback.

Runner availability recovery is tracked separately in issue #182 / PR #183.
The inspection preview defaults to Status on the existing completed run; starting
its API does not grant or consume another model turn. Fresh work needs its own
approved allowance. The API should remain available after the limit is reached.

The shared Agent editor rejects discovery responses for an older model or runner
selection. It preserves a reasoning-effort edit only while that value remains in
the newly selected model's native options; a no-effort model switches to
`default`. Searching the model list keeps the selected friendly label visible.

Skill References are optional. An Agent can execute its task with no connected
Skill node; the request and run history record an empty skill list. Connected
skills still require immutable revisions and retain hash, duplicate and count
validation. Resume keeps the original run's selected skill set, including none.

The [no-skill example](no-skill-flow.json) is a real single-Agent Fresh graph with
no Skill node or Skill Reference. Its [native proof](no-skill-proof.json) records
one approved Claude subscription turn, the empty pinned-skill list in the prompt, the native
answer and usage, unchanged workspace, and the preserved ledger increment1to2.
The graph remains in Fresh mode; the local verification ceiling is exhausted
after that one approved turn. View its recorded result through Activity without
starting another inference.

Normal services do not inherit the historical verification ceilings below.
Those are archived experiment allowances, not runtime configuration.
