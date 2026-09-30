# Issue #123: trace completeness spike

This is a zero-model-call spike for
[specs issue #123](https://github.com/amadou-6e/specs/issues/123). It reuses
the bounded Codex observations from #120 and the synthetic Docker Skill Draft
run from #146. The Claude #121 spike stopped before a model call because the
native CLI and dedicated credential were unavailable. No Claude trace or
equivalent cross-provider task is claimed.

## Evidence and scope

- `sanitized-codex-pairs.json` contains two actual `response_item` call/result
  ID pairs extracted from the private #146 rollout. The sanitizer accepts only
  native ID patterns and copies no prompt, command, output, path, or credential.
- `probe_agentviz_import.mjs` runs AGENTVIZ's bundled `parseSession` against a
  private rollout and prints structural counts and native IDs only. On the
  #146 two-turn rollout, 50 raw JSONL records produced 14 normalized AGENTVIZ
  events, two turns, four tool calls, and four attached outputs, with zero
  parse issues. Each normalized event retained a native payload ID under
  `raw.payload.id`. This is an import check, not proof that every raw event
  becomes a display event.
- `project_trace.py` is an intentionally small projection prototype. It takes
  already sanitized envelopes, preserves receipt order and source IDs,
  deduplicates only repeated `(source, source_event_id)` pairs with identical
  payload digests, rejects conflicting reuse of an ID, links tool calls
  and results by explicit call ID, and keeps missing usage distinct from zero.
  Its tests use synthetic fixtures, so they do not prove provider reconnect
  behavior. A Codex item ID shared by `item/started` and `item/completed` is
  a call-link ID, not a unique event ID; leave `source_event_id` null unless
  the source supplies an event-specific identity.

Raw rollouts, app-server streams, and the ChatGPT login remain outside Git.
The Langflow container was not running during this spike. #118's earlier
read-only trace observation is the Langflow input: its outer APIRequest span
reported `totalTokens: 0` while Codex had token usage, and the run/thread IDs
were embedded only in output text. This spike did not recreate that flow.

## Reproduction

The projection and sanitizer use only Python's standard library:

```powershell
python -m unittest discover -s experiments/feasibility/123 -p 'test_*.py' -q
python experiments/feasibility/123/sanitize_rollout_sample.py '<private-synthetic-rollout.jsonl>' '<sanitized-output.json>'
```

For the AGENTVIZ import check, use a checkout with dependencies already
installed. The authoring machine's Node v20 could run esbuild but not its
installed Vitest, so this uses the installed esbuild directly:

```powershell
node_modules/.bin/esbuild.cmd src/lib/parseSession.ts --bundle --platform=node --format=esm --outfile='<ignored-parser-bundle.mjs>'
node '<laomedo>/experiments/feasibility/123/probe_agentviz_import.mjs' '<ignored-parser-bundle.mjs>' '<private-synthetic-rollout.jsonl>'
```

Run this only on a synthetic private runner trace. The import script prints
native IDs and structural counts, so its output still deserves review before
sharing. It does not copy or publish the raw file. No new model turn or
credential handoff is required.

## Decision

Codex private-rollout import into AGENTVIZ is feasible for this sample. The
full #123 cross-provider trace contract is **not verified**: Claude has no
credentialed trace, the Langflow outer span is not structurally correlated to
the private run, and interruption/reconnect semantics are tested only in
synthetic projection fixtures. Treat missing fields as unknown or unsupported,
never as zero or inferred use.
