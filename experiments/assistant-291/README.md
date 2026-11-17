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


## Compact category consent delta (2026-11-17)

Production f2a5fca5134373b408147f8641a8483b94fa0c94 / spec
95896355b5b9dc9fa693209cb68b3caec9d8f8ea implements the owner's selected
Rename/Edit/Run categories and any-graph-in-this-conversation Always consent.
54 assistant tests and 21 subtests, 23 UI tests, build, Black and exact-head CI pass.
The first checkpoint had a mechanical extra SQLModel.get argument; tests caught
it, it was corrected, and the full suite then passed. Retained app startup exposed
a missing pre-upstream permission-table initialization; corrected and real retained
chat database now starts. An old schema-bound native thread refused resume before
MCP effects; a fresh linked conversation preserves its history and works.

Real integrated-browser/native Codex acceptance: initial rename pending, human
Always approve renames changed first graph; later native rename on a second graph
succeeded under that grant while an Edit stayed pending. Human Ask every time
revoked Rename; a subsequent rename stayed pending. Human Always approve runs
executed the known disposable ChatInput/Output graph; a later native proposal ran
under consent. Read-only proof.py corroborates two completed jobs with exact
owner/flow/run identity. Pending Edit/Rename were not applied. All test conversation
grants are revoked at end. Screenshots and private database/session remain outside
Git. No broad component/provider/native-permission/publication acceptance claimed.

This delta is fully unreviewed: Claude's existing session refused for quota until
20:00 Europe/Berlin. Owner selected waiting for reset. Earlier approval covers
only 2e0f87cb/76784e8. Both PRs remain draft and unmerged.


Presentation follow-up a394a6fcc6ce6259e84a5b4721a8f9a75a2b9384 / spec
11c36d96688e1cc627bfba65cc6fdc84bdd985a0: user removed Details and requested
quieter muted text, top-right graph icon and small settled operation/change/outcome
cards. All 23 UI tests, build, Black and spec validation pass. Actual retained
integrated chat was reloaded and the small Rename/Run outcome cards verified.
No backend/consent change, no extra model probe. User independently approved the
previously pending rename while inspecting the app; its retained card now says
Renamed. Screenshots remain local. Review still waits for the selected quota reset.


Final layout 04bbed456d4e00a32f7ff01ef8195328f50fe9fc / spec
0dbd8f488266750cf1e2860fc069a81a74369721 unifies all three categories as
one muted sentence, icon top right, outcome below left.25 UI tests/build/Black/
spec validation pass. render-retained.mjs captures actual retained expired Edit,
successful Rename and completed Run in an independent browser, without prompts or
graph mutations. All three inspected by the implementer; screenshot files remain
private local evidence. Same reviewer awaits20:00Berlin reset; no merge.
