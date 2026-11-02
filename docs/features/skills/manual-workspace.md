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

This control revision is undergoing real-browser and independent review. The
following evidence and images describe the earlier control model and do not
establish acceptance of this revision.

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
