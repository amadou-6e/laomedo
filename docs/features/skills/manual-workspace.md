# Skill workspace

Open Skill files from the Skill node. Authorised text files are immediately
editable; the workspace opens the journal head while the graph keeps its pin.
Skill ID and short revision share a single header line. The Skill summary remains
visible and its overview can be expanded.

Change any existing text file to reveal the bottom-right **Discard** and
**Publish** controls. Switching files, Find and historical comparisons preserve
working text. An optional commit message defaults to `Update Skill files`.

**Publish** saves the complete changed-file batch as one immutable commit, then
promotes that exact revision to registry current. The footer lists all files to
publish against registry current, including earlier saved changes. Choose a path
to inspect its cumulative diff in the main editor. There is no separate Edit or
publication-review mode. Git publication remains deferred.

**Discard** asks for confirmation, clears working changes and reloads the journal
head. It never deletes saved history or changes registry current. Closing with
working changes also asks first. Uncertain writes retain their exact identity and
require **Check result** before closing or starting another write.

If saving succeeds but promotion fails, the saved candidate remains traceable,
and the footer offers retry or discard. A definitive failure permits a new
explicit attempt after inspecting refreshed changes. An unknown result must be
reconciled first. Policy/grant refusals preserve working text. Retry edit controls
recovers restored permissions; Retry comparison reloads an unavailable base.

The host service requires its explicit `--manual-permissions` JSON, keyed by
Skill ID with `edit` and `publish` booleans, plus the existing edit policy.
Missing grants deny writes. Backend provenance is `operator`, not an independently
verified human identity. Manual creation/deletion/binary edits, per-user ACL, Git
publication and durable unsaved crash recovery remain unsupported.

## Current control revision

![Actual always-editable Skill with compact header](assets/always-on-clean.png)

![Actual changed-file footer with Publish and Discard](assets/always-on-dirty.png)

Recorded 2026-11-02 in the actual authenticated local Skill viewer on Windows,
headless Edge, frontend source `e54015b6caf77bd4af0a3861adfe11450d702449`, pinned Langflow
`fec71dca901949c09ed4d63315804337cd2eb13d`. These are real registry files and
immutable commits, with no Agent run or GitHub mutation for this change.

| Story | Observed result |
| --- | --- |
| Always-on editing and density | Authorised head opens editable; removed mode/latest controls absent; Skill ID and SHA share one line; graph pin hint and summary remain visible. Native typing retains spaces. |
| Conditional actions | Footer absent while clean, appears after a file change; restoring text or confirmed Discard hides it without writing. Publish/Discard stay in bounds at 900 by 650 full page. |
| Atomic publication | One Publish saves two changed files once and promotes the exact candidate, including earlier saved changes. Registry bytes match the full submitted batch; durable receipt replay confirms the same result. |
| Cumulative disclosure | Full changed-file count includes earlier saved commits; selecting a path opens its registry-to-working-copy diff. |
| Comparison recovery | A browser-level block of the uncached registry-base request (no substituted HTTP response) disables Publish. Escape dismisses only the card; unblocking and Retry comparison preserve text and restore Publish. This is browser transport fault injection, not a naturally occurring service outage. |
| Permissions and display | Actual grant removal enforces read-only; restore/reopen restores editing. Actual application Dark mode and full-page/restore retain the footer and working state; Light mode is restored. |

At this check the real example retains 13 history entries. Older
snapshots, both original Skill graph pins and source bundles remain unchanged.
Sixty-eight internal frontend tests pass; Skills, architecture and error catalogue
guards also pass. Those controls support the browser checks and do not replace them.

The earlier always-on source `0b659ec` additionally exercised real browser offline
save reconciliation (same UUID/batch), live publication-grant refusal with retained
candidate, grant restoration/promotion, invalid-batch refusal, stale edits, native
unload, Find/history navigation and an actual history-service stop/restart. Its
initial viewport check raced resizing; a settled follow-up passed. Cached offline
comparisons did not exercise an uncached failure and are not reported as that path.
The final source fixes the comparison card's native Escape handling found by the
uncached check. Lost responses after committed effects and crash recovery have
internal coverage, not a new live crash demonstration.

A message applies to the next new commit. Once saved, that commit and its message
are immutable; retrying only its publication does not amend the message. A saved
candidate is retained if promotion fails. Reopening an unpublished head alone
keeps the footer hidden until a fresh file edit, as requested.

Final requesting-owner validation remains pending. Earlier records below describe
the superseded controls and their own source revisions.

## Earlier control-model verification

Recorded 2026-11-02 on Windows with headless Edge, actual saved graphs and local
registry. App/frontend source `be7d83cbf635b0a53b6b0162a8848fbe4a0843b7`, pinned Langflow
`fec71dca901949c09ed4d63315804337cd2eb13d`. The dedicated preview uses a confirmed
Windows selector event loop; this is not a product-wide backend recovery fix.

| Actual path | Observed result |
| --- | --- |
| Search and navigation | Nested disclosure, native Space/Enter, exact Seti glyph, current-source focus/read-only protection, unsaved-text search, global Open/Collapse all and query retention pass. |
| Multi-file save | Real two-file batches create immutable commits; final saved bytes independently match the complete submitted file contents. Eight genuine history entries are retained, including earlier real checks. |
| Policy and permission recovery | Atomic policy refusal and actual service-grant revocation keep buffers. Save re-enables after state reload; Retry edit controls recovers restored permission. |
| Reconnection and unknown write | Actual browser offline failure retains request and close notice. Online refresh preserves the workspace; Check result reuses the exact UUID/batch and creates one commit in 4472 ms. |
| Comparison and publication | Real comparison failure, Escape and Retry recover. Publish remains reachable beside a retained global error; exact candidate promotion confirms in 239 ms. Replaying the same real receipt confirms the same result. |
| Concurrency | A stale working-copy save and older publication both refuse; explicit recovery preserves or discards text only after confirmation. |
| History outage | Exact task-owned service stop/restart preserves the journal. Find stays usable; same-dialog Retry restores eight entries in 157 ms, then Retry edit controls recovers. |
| Display | Full page/restore, 900 by 650 viewport and actual Light/Dark settings pass; the dedicated browser's original theme is restored. |
| Boundaries | Original Skill graph pins, immutable snapshots and source bundles remain unchanged. No new Agent/model dispatch or GitHub effect; existing GitHub grants remain revoked. |

Served JS/CSS bytes match the frozen build. Sixty-two frontend regression controls
pass; thirteen installed manual/auth/route tests pass in the Langflow environment.
Core-only CI explicitly skips optional FastAPI route tests. These internal controls
support the real paths above and do not replace them or requesting-owner validation.

Earlier actual checks found and repaired inert modal cards, Escape propagation
and a canvas-refresh lifetime defect. Earlier saved commits remain in the real
history; they were not reset or manufactured. Normal canvas layout, handle and
unavailable Agent/GitHub discovery metadata refreshed during testing; whole-flow
byte equality is not claimed. The Skill references were independently read back.
No new Agent execution or current GitHub discovery acceptance is claimed.

The offline check loses connectivity before dispatch; confirmed receipt replay is
also verified. Lost responses after a committed effect, crash interruption and
revoked-policy reconciliation have internal regression coverage, not a new live
fault demonstration. The native browser-close warning was also observed with actual unsaved text;
cancelling close kept the text, then explicit discard left the registry unchanged.
Unsaved buffers have no durable browser reload/crash recovery.
Manual creation/deletion/binary editing, per-user ACL and Git publishing are
unsupported. Claude approved code at `fbd3bd9`, specification at `32bc8e6`, and
the actual rendered UI at `be7d83c`; later wording fixes address its nonblocking
notes. The reviewer assessed installer wiring and live evidence; its file tool
could not open two frozen frontend files outside the workspace. Both PRs remain
unmerged pending the requesting owner's inspection and validation and the
accepted specification merge order.
