# Skill workspace

Open Skill files from the Skill node. Authorised text files are immediately
editable; the workspace opens the journal head while the graph keeps its pin.
Skill ID and short revision share a single header line. The Skill summary remains
visible and its overview can be expanded.

Right-click a file, folder or empty space in **Files** for Upload files, Rename,
Delete and Copy relative path. Shift+F10 or the Menu key opens the same
menu for the focused target. Move files/folders with drag/drop; Ctrl+X and Ctrl+V
provide the keyboard equivalent without a Move to menu. Drop local files into Files to import them; upload on a file
targets its parent, and empty space targets the Skill root.

F2 or Rename edits the filename in place with a blue border. Enter or blur
commits, Escape cancels. Renames and moves retain working text and binary bytes.
Delete removes files immediately; Files-focused Ctrl+Z restores them and Ctrl+Y
or Ctrl+Shift+Z reapplies. Deleting a subtree and undoing restores its dirty text.
Editor/input shortcuts remain native. Undoing an upload removes that file, including
subsequent edits to it. A new file action clears redo; confirmed save/discard clears
tree history, while a refused/uncertain save retains it. Following a different
revision clears old buffers and tree history so stale actions cannot replace new bytes. Required SKILL.md stays at the root. These actions are staged until
Publish; Discard restores saved files. No automatic overwrite occurs.

Change any existing text file to reveal the bottom-right **Discard** and
**Publish** controls. Switching files, Find and historical comparisons preserve
working text. An optional commit message defaults to `Update Skill files`.

**Publish** saves the complete changed-file batch as one immutable commit, then
promotes that exact revision to registry current. The footer lists all files to
publish against registry current, including earlier saved changes. Choose a path
to inspect its cumulative diff in the main editor. There is no separate Edit or
publication-review mode. Git publication remains deferred.

**Discard** opens a centered popup. Keep editing, Escape or clicking outside
closes only the popup and preserves working changes. Explicit Discard changes
reloads the journal head. It never deletes saved history or changes registry
current. Closing with
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
verified human identity. Binary in-place editing, directory imports, per-user ACL,
Git publication and durable unsaved crash recovery remain unsupported.

## Preview and Discard popup: current verification

Binary preview fills the available editor content area without a byte-count/hash
row or preview frame. Images have no added padding and scale to fit with their
aspect ratio kept;
the existing Full page control enlarges the workspace. Other binary formats retain
a scrolling paged byte view. The source bytes and preview safety rules are unchanged.

A completed rename has no visible outline or border. Keyboard focus uses a blue
row fill; the in-place rename input keeps its blue border. Discard confirmation is
a modal popup, not a banner inside the editor. Initial focus is Keep editing. Tab
and Shift+Tab stay inside; Escape and outside click cancel without changing text.
Explicit confirmation reloads saved files. Dirty Close, outer Escape and outer
outside click use the same popup, closing the workspace only after confirmation.

![Actual full-area image preview](assets/preview-fill.png)

![Actual centered Discard popup](assets/discard-popup.png)

![Actual filename focus after rename](assets/rename-focus.png)

![Actual popup at 900 by 650](assets/discard-popup-small.png)

Captured 2026-11-03 in authenticated headless Edge on Windows, runtime
`00657129879be566b7f1a03836d771f825c3848d`, with pinned Langflow
`fec71dca901949c09ed4d63315804337cd2eb13d`. The PNG shown inside the preview is an
actual historical screenshot asset; its embedded old UI is part of that image.

Actual browser checks cover saved/staged raster fit, byte-view metadata removal,
Enter/blur rename focus, normal/full-page 900×650 and Dark/Light. The popup leaves
editor geometry unchanged, safely cancels on initial Enter, traps focus, restores
the opener and preserves exact text on cancellation. Backspace, Delete and
Ctrl+Z/Ctrl+Y inside it leave canvas nodes and text unchanged. Explicit discard and
dirty close/reopen restore the saved text and unchanged 18-entry history. The
browser recorded zero page errors, graph dispatches or registry writes. All
temporary imports/edits were discarded; Light theme and clipboard were restored.

Tailwind expresses outline suppression as a transparent 2px outline; actual row
borders and ring dimensions are zero. Computed focus colours are Light #005fb8
with white text and Dark #4aa0ff with black text. Screenshots show no black row
contour. The browser waits for the existing resize animation and actual edit-control
refresh before measuring or issuing another action; the initial helper observations
are retained separately and are not reported as passed runs.

Internal frontend controls (92 across 15 suites) supplement the actual paths.
This change adds no save/replay logic and does not claim live lost-response/crash
recovery. Requesting-owner validation remains required before merge.

## Earlier explorer verification at bc7c0eda (historical)

Empty folders stay in the open workspace after their last file moves/deletes,
including after Publish. They accept drops/imports and can be renamed, moved or
deleted. **Empty · not saved** distinguishes local directory state: registry
commits store files only. Reopening reconstructs folders from saved files; Discard
restores saved structure. No hidden placeholder file is created. Folder-only
actions do not enable Publish. Drop targets use grey highlighting only.

JSON files use a braces icon. Existing and newly imported raster images have an
automatic preview: PNG, JPEG, GIF, WebP and ICO are identified from bounded bytes.
Other binary files show paged hex/ASCII; an undecodable image falls back to bytes.
SVG, HTML and PDF are never executed as documents. Binary preview is read-only.

![Actual inline filename rename and JSON braces](assets/explorer-inline-rename.png)

![Actual grey-only pointer drop target](assets/explorer-grey-drop.png)

![Actual saved raster image preview](assets/explorer-binary-preview.png)

![Actual publication with retained empty folder](assets/explorer-published-empty.png)

Captured 2026-11-03 in authenticated headless Edge on Windows, runtime
`bc7c0eda233757b3bf360e5d3a8262e2c10c7569`, pinned Langflow
`fec71dca901949c09ed4d63315804337cd2eb13d`. The displayed PNG is a real, retained
workspace screenshot asset, so its contents show an earlier UI. It is evidence of
binary rendering, not a current UI reference.

| Story | Actual observation |
| --- | --- |
| Empty folder and moving | Pointer move of final child retains labelled folder; import of actual repository JSON into it succeeds. Grey target has no outline or shadow. Ctrl+X/V also moves; no Move to menu. |
| Rename | F2/native Menu key, stem selection, in-row blue border, Enter, invalid-name error/recovery and Escape pass. 900×650 and Dark/Light checked. |
| Delete and undo/redo | Immediate dirty subtree deletion has no confirmation; Files Ctrl+Z restores exact unsaved text and Ctrl+Y deletes again. Native editor undo remains independent. |
| Preview | Actual saved/imported PNG decodes. Actual installed Monaco font has exact first 16 bytes in paged hex; Show more expands. No document embed is used. |
| Save and restore | Two real UI save/promotions move the operation file out, verify the empty folder survives Publish, then restore the maintained paths. Confirmed save clears undo. Eighteen genuine commits remain; original revision bytes and graph pins are restored/preserved. |

No application Agent/model run or GitHub write was needed. Temporary JSON/font/
image imports and text edits were discarded. Source bundles, original Skill pins,
manual grants and Light theme remain unchanged. Independent review, internal
controls and CI supplement these actual paths; requesting-owner validation remains
required. No live post-effect response-loss/crash recovery claim is made.

The pinned Monaco 0.57.0 JSON worker imports editor contributions lazily. The
viewer registers that module before its first standalone editor to avoid missing
service errors. The final actual run requires zero page errors; preserve that
regression check when upgrading the pinned frontend/editor.

## Earlier file-action verification at 2b5fe172 (historical)

![Actual file context menu](assets/file-actions-menu.png)

![Actual deleted-file revision comparison](assets/file-actions-history.png)

![Binary metadata remains visible in a narrow window](assets/file-actions-narrow.png)

Captured 2026-11-03 from the authenticated local Skill viewer in headless Edge on
Windows. UI source `2b5fe172fccbb3b761eb6a8674703668d849778a`, pinned Langflow
`fec71dca901949c09ed4d63315804337cd2eb13d`. These images show real registry files
and retained revisions. The local example has 16 commits and three current files.
The Source/Preview row is one icon beside the scrollable file tabs; its accessible
name and tooltip describe the destination. Preview uses working text.

| Story | Observed result and source |
| --- | --- |
| Context menus and keyboard | Final UI: pointer, Shift+F10 and native Menu key retain the selected target. Escape closes the menu/form and returns focus to its row. Root menu covers blank Files space. |
| Working file actions | Final UI: actual multi-file picker imports Markdown and an existing 209,352-byte PNG; rename, pointer move, keyboard Move to, relative-path copy, delete/cancel and Discard pass. The saved three-file tree and history remain unchanged after temporary edits. |
| Layout and grants | Final UI: 900 by 650 full-page menus/forms and the complete binary hash stay visible. Actual Dark mode works; Light is restored. Revoked local grants disable mutations and external drops while Copy remains available; grants are restored. |
| Failure and recovery | Final UI: real name collision, invalid rename, oversized local file, directory drop and exclusive OS file lock refuse the whole operation. Unlock/reselect recovers reading. An actual non-secure local origin has no Clipboard/WebCrypto API: manual path copying and the bundled binary hash still work. |
| Atomic publication | Source `7973c31`: original policy refuses the real two-file batch without a commit; explicitly admitting the example's asset paths permits one atomic UI save/promotion. Independent stored-byte hashes match the original document and PNG. |
| Binary moves and history | Source `7973c31`: saved binary moves resolve immutable before-bytes, with deletions in the same commit. Browser transport blocking before a save locks mutation/close; Check result replays the exact UUID/base/payload, then promotes once. Size/hash and removed text are inspectable in per-file history. |

The final UI changes after `7973c31` are the Menu-key portal guard and narrow-window
binary-hash wrapping, plus their regression checks. Transaction hooks, working-tree
helpers, publication controls and all packaged backend bytes are unchanged;
publication evidence is retained at its original revision. Final UI working and
failure paths were rerun. An authenticated API save of the existing image supplied
a second nonempty folder for the folder-action story; that setup is recorded as an
API operation, and the subsequent rename/move/delete/Discard uses the actual UI.

All three new commits were independently checked against raw stored files:
parent chain, complete changed-path sets, tree hashes and retained diffs match.
Earlier snapshots, source bundles and both saved graph Skill pins remain unchanged.
The original Agent attempt count and prior GitHub effects remain unchanged.
Eighty-six internal frontend checks pass; the Skills suite and architecture/error
catalogue checks support the live paths. They do not replace owner validation.

Binary contents are metadata-only; valid UTF-8 without NUL remains text regardless
of suffix. The host must explicitly permit asset paths, additions/deletions and
publication. Protocol bounds are 128 files, 512 KiB/file and 4 MiB per bundle;
the 4 MiB encoded request admits less new binary data because of base64 overhead.
No file executes or publishes to Git. Directory uploads, empty folders, binary
content editing and durable unsaved crash recovery are unsupported. Transport
blocking above occurs before transmission; lost replies after a committed effect
have internal coverage, not a new live crash test.

The final requesting-owner inspection remains pending; both PRs stay unmerged.

## Earlier always-on control verification

The following captures and records precede the file actions and single preview
icon above. They retain their original source revisions.


![Actual always-editable Skill with compact header](assets/always-on-clean.png)

![Actual changed-file footer with Publish and Discard](assets/always-on-dirty.png)

Recorded 2026-11-02 in the actual authenticated local Skill viewer on Windows,
headless Edge, frontend source `e54015b6caf77bd4af0a3861adfe11450d702449`, pinned Langflow
`fec71dca901949c09ed4d63315804337cd2eb13d`. These are real registry files and
immutable commits, with no Agent run or GitHub mutation for this change.

| Story | Observed result |
| --- | --- |
| Always-on editing and density | Authorised head opens editable; removed mode/latest controls absent; Skill ID and SHA share one line; graph pin hint and summary remain visible. Native typing retains spaces. |
| Conditional actions | Footer absent while clean, appears after a file change; confirmed Discard hides it without writing. Publish/Discard stay in bounds at 900 by 650 full page. |
| Atomic publication | Publish saves two changed files once. A refused promotion retains the candidate; restoring permission and retrying promotes it without another save, including earlier saved changes. Registry bytes match the full submitted batch; durable receipt replay confirms the same result. |
| Cumulative disclosure | Full changed-file count includes earlier saved commits; selecting a path opens its registry-to-working-copy diff. |
| Comparison recovery | Publish stays disabled during a browser-level block of the uncached registry-base request (no substituted HTTP response). Escape dismisses only the card; unblocking and Retry comparison reload the base and preserve text. Publish also requires current grants. This is browser transport fault injection, not a naturally occurring service outage. |
| Permissions and display | Actual grant removal enforces read-only; restore/reopen restores editing. Actual application Dark mode and full-page/restore retain the footer and working state; Light mode is restored. |

At this check the real example retains 13 history entries. Older
snapshots, both original Skill graph pins and source bundles remain unchanged.
Sixty-eight internal frontend tests pass against the `e54015b6` source. Skills,
architecture and error catalogue guards passed at `0b659ec`; later runtime changes
only affect editor input and Escape handling, plus recovery wording. Those controls
support the browser checks and do not replace them.

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
