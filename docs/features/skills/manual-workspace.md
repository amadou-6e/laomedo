# Manual Skill workspace

Open **Skill files** on the Skill node. The viewer opens its exact pinned revision.
If that revision is older than the editing head, choose **Open latest editable
revision** explicitly; this does not change the graph's pin.

The header uses icon-only Full page and Restore window controls. Files have the
VS Code Seti Markdown glyph and Codicon folder arrows. Find is a collapsible
workspace search with nested folder, file and matching-line rows. It includes
unsaved text while editing. Open/Collapse all also covers search groups.

## Edit and save a candidate

Choose Edit, change one or several existing text files, and enter a commit message.
Switching files retains the working text; modified tabs have a dot. Save commit
validates the complete batch and creates one immutable history entry. A saved
candidate does not change registry current. Selecting an earlier commit in read
mode compares only the selected file against the current viewed revision.

![Actual two-file working copy](assets/manual-editing.png)

Edit and Publish require separate explicit local service grants plus the existing
versioned edit policy. The operations service accepts an optional
`--manual-permissions` JSON file, keyed by Skill ID with `edit` and `publish`
booleans. Missing permissions deny writes. Configure this file on the host; the
browser cannot provide policy, tickets or provenance. This preview enables only
`pr-feedback-title`. Backend provenance is `operator`, not a verified human identity.

## Review and publish to the registry

Choose Review publication after saving. The changed-file list covers the exact
candidate's cumulative changes against registry current. Select a file to see its
visual diff; the viewer does not concatenate patches. Choose Publish revision to
promote that exact reviewed candidate. A changed base or head refuses the action.

![Actual per-file registry publication review](assets/manual-publication-review.png)

![Actual published registry revision and retained history](assets/manual-published.png)

Publishing changes registry current only. Existing graph pins, source files and
Git repositories keep their existing values. Git publishing is deferred.

## Failure and recovery

A refused batch retains the working copy without a partial commit. Policy refusal
allows correcting the files and saving again. A revoked grant retains text; after
restoring local configuration, Retry edit controls refreshes the controls.

A stale edit exposes Open latest editable revision while editing. Copy wanted
working text before discarding; Keep editing preserves it, and Discard changes
explicitly opens the newer head. Closing unsaved text also asks for confirmation.

An uncertain save retains its exact request and offers Check result. Closing and
discarding cannot cancel a pending write. Temporary network reconnection and
canvas refresh retain the viewer, working files and pending identity, so Check
result can reconcile the same request. Comparison failure disables Publish and
exposes Retry comparison. History failure leaves local Find usable; Retry restores
history after the service returns.

Focused error cards support Dismiss and Escape without closing the Skill viewer. Unrelated
background notifications are hidden during the modal, retaining their state and
reappearing after close. They cannot cover Publish.

![Actual application Dark mode](assets/manual-dark.png)

## Recorded verification

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
fault demonstration. Unsaved buffers have no durable browser reload/crash recovery.
Manual creation/deletion/binary editing, per-user ACL and Git publishing are
unsupported. Both PRs remain unmerged pending final reviewer completion and the
requesting owner's inspection and validation of this revision.
