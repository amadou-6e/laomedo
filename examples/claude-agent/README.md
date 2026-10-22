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
