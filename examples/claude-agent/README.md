# Claude Code Agent

The Claude node uses the shared Agent ports with your existing Claude Code
subscription. It has its own provider/session identity, pinned skill context,
status/cancel/resume, output validation and bounded same-session correction.
Answer, Run Reference and Submission share one dispatch per node build.

This first mode proposes changes; connected Skill/PR operation nodes apply
authorized edits. Native command/file tools and MCP are disabled. It is a host
CLI adapter, not an isolated writable coding environment. Pinned skill files are
included as context, not native skill discovery. Personal customizations and
auto memory are disabled. No authentication files are read or copied by Laomedo.

Install the whole component category alongside the runtime (the Claude client
inherits the existing Agent client). Start the host service with:

```powershell
python -m laomedo.claude_runner --state <private-state> --skill-store <registry> --source <source> --executable <claude-executable> --max-model-turns 3 --port 8769
```

Set `LAOMEDO_CLAUDE_RUNNER_TOKEN_FILE` in the Langflow host to the runner's
private `api-token` file. The graph contains a loopback runner URL, never a
credential. The default runner turn budget is zero. CLI version is pinned to
2.1.301. Invalid/foreign run references and conflicting output pins are refused.
Host post-turn validation is supported; a precheck tool is not installed.

See [protocol](PROTOCOL.md) for the bounded real verification. The real Skill edit and same-session resume verification passed; internal tests
are recorded separately. The intended working graph
is Skill -> Claude Answer -> the same Skill Operation input. The resulting
candidate has the normal immutable history/diff and backend run provenance.

Official references: [CLI](https://code.claude.com/docs/en/cli-reference) and
[programmatic runs](https://code.claude.com/docs/en/headless).

Claude Code retains resumable session transcripts under the operator's normal
Claude profile. Their location and retention are controlled by the official CLI,
outside Laomedo's run-state boundary; the reviewer does not read them. Exported
graphs contain neither login material nor raw transcripts. Only UTF-8 skill files
are included; skipped binary paths are recorded explicitly. Parent CLI exit is
observed, while descendant cleanup and complete SDK evidence remain unknown.

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
