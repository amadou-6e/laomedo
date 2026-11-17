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

Final production head 2e0f87cb29d4d56fc11c8639c0cd3f54340fd70e; spec head
76784e87d0a4b64faacb0693511d8ce0a6c3dc3a. The real workflow evidence above
covers production through 6b930924. Final connection protection and session-aware
read projection passed affected tests; preview was reloaded with those changes.
No live attack acceptance is claimed for that final backend delta.

52 assistant backend tests and 21 subtests passed before the final session
projection refinement; affected actions/catalog/MCP checks then passed 20 tests
and 21 subtests at final head. All 20 UI tests, 63 pinned component tests with
isolated initialized settings and 49 subtests, and 587 diagnostic UI checks pass.
The earlier uninitialized settings invocation failed five component controls;
it did not establish a product regression. Black, frontend build and exact-head
CI pass. Spec validation has zero errors and one existing large-diagram warning.

Claude independently completed cumulative full substantive code review and final
specification review: APPROVE. All twelve supplied actual renders, including A4,
were inspected: visual APPROVE for the recorded 1041x895 path. Name-conflict and
truthful-outcome findings were verified fixed; apparent diagnostics reverts came
from a mistaken review-packet base, never from the feature's actual own-diff.
No later production changes. Another-session read-only card has backend/UI
coverage but no independent screenshot; mobile, keyboard and screen-reader
acceptance is not claimed. Recorded initial wiring failure remains explicit.

Publication and native provider permissions remain excluded. Both feature PRs
remain draft and unmerged. No broad provider/component acceptance is claimed.
The user's original app stays untouched; the isolated integrated preview retains
real outcomes. The final unused rename expired without effect.
