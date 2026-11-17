# Assistant graph-action acceptance (#291)

This exp-only concern owns disposable real-app/provider/editor acceptance.
serve.py creates independent private app/database/runtime state and never submits
a model prompt on startup. It preserves the owner's existing chat app. Sources
use task branch feat/291; production tests never import this harness. Screenshots,
tokens, private databases and local metadata remain outside Git.


Checkpoint 6b930924 (spec target 368a767): native MCP proposed graph field edits,
rejection left the saved graph unchanged, and human app approval changed only the
requested field while preserving other graph bytes. Editor remained open; both
pending/result cards warned about reloading before saving. An initial graph run
correctly failed because the experiment seeded its edge into context_id rather
than input_value. A further native proposal repaired only that connection after
approval, preserving every node; a newly approved run then completed. Independent
read-only job lookup confirmed completed status, matching action/run ID and exact
owner/flow. Outcome cards persisted after browser reload.

The first tool discovery refused before native inference because the runtime
still expected six tools; production now derives its check from the nine-tool
allowlist. A new editor tab's native auto-login rotated the experiment cookie;
the first browser rejection was refused, with no effects. Opening the editor
before proposing kept proposal/decision in the same originating app session.
The UI now suppresses decisions from another session and requests a fresh proposal.

49 assistant backend tests/14subtests,20UI tests,63 pinned component tests with
isolated initialized settings/49subtests and587 diagnostic UI checks pass.
The earlier uninitialized settings invocation failed five component controls;
it did not establish a product regression. Full Black/build/exact-headCI pass.
Initial code review is partial and requests corrections; focused correction,
remaining tests/settings coverage and independent actual-render review pending.
No merge or broad provider/publication acceptance is claimed.
