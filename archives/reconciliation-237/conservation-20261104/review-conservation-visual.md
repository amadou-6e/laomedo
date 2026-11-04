**VISUAL_CONSERVATION: APPROVE, for the restored paths only.** In the screenshots, the restored Skill error and preservation paths render as designed, and the result records report each story passing. I found one Medium problem: the screenshot of the unsafe current revision shows a second, contradictory error card. It comes from the later manual-editing path, not from the restored code, so it doesn't block this verdict. It does need fixing before owner acceptance of SK-02/SK-06.

## What I opened
- **All 11 PNGs**, each read visually:
  - `browser-validate-final/`: viewer, history-diff, workspace-search, binary-full-page, discard-confirmation;
  - `browser-conservation-errors-1/`: unsafe-current, unsafe-comparison, offline-comparison, keyboard-and-background-refresh;
  - `browser-source-conservation-final/`: source-refused, my-skills-discovered.
- **All three `result.json` files**, in full.
- **`skills-followup-206/docs/features/skills/user-stories.md`**, in full.

## What the images show
- **Compact single typography.** The interface uses one sans-serif face and the editor uses monospace. Every image is consistent, with no mixed or oversized type inside the viewer.
- **Selected-file history comparison** (history-diff).
  - It shows one file only, labelled "Selected revision 4f0efb08 → Current 22ef4312".
  - Changed lines are highlighted red and green, and a line-ending note reads "14 CRLF; current 19 LF".
  - There is no raw `diff --git` text. The "Current source" link is visible.
  - The result record shows 18 real history entries.
- **Workspace search.** Find shows 16 matching lines in 2 files, grouped under the file tree with highlighted matches and a case toggle.
- **Full-page binary preview.** The PNG asset previews inside the expanded workspace, with the restore control in the top right.
- **Discard confirmation.** The dirty tab dot, the "1 file to publish" footer and the Publish/Discard buttons are present. The focused dialog offers Keep editing and Discard changes. The record shows `registry_writes: 0`.
- **Unsafe current revision.**
  - Shows title, explanation, recovery text, and Technical details containing only `"code": "skill_revision_unsafe"`.
  - The copy icon is in its confirmed state, and **there is no Reload files button**.
  - The record shows `clipboard_contains_only_own_error: true`, and cleanup removed the alias and restored the original bytes and link count.
- **Unsafe historical comparison.**
  - Same refusal with no Reload. The stale diff is cleared, and Current source remains available for recovery.
- **Offline comparison.**
  - Shows the neutral fallback ("The reason has not been established"), the code `skill_comparison_unavailable`, and a **Reload files** button.
  - The record shows the same GET (`4f0efb08`) succeeding again after going back online.
- **Keyboard and background refresh.**
  - The text typed on line 21 ("Conservation browser keyboard check.") is still there, the tab is still dirty and the Publish bar is still showing.
  - A static image can't prove that keys never reached the canvas, or that the editor stayed mounted through reconnect and focus. Those come from the story records and the request log (session, config and builds refetch), not from the picture.
- **Source discovery.**
  - The refused source shows an inline error and "No source found".
  - The `my-skills` source recovery lists 51 options, matching the record, with no success banner.

## Findings
1. **Medium: an extra, contradictory error card on the unsafe current revision.** The bottom-right card in unsafe-current reads "Skill edit controls are unavailable… Use Retry edit controls to reconnect." It sits beside a "Retry edit controls" button at the top left.
   - **Cause:** it comes from the separate `POST /laomedo/skills/manual/editor` read. That request is in the errors log next to the refused GET.
   - **Why it matters:**
     - The main panel says the revision is permanent and can't be repaired.
     - The card blames a connection problem, which is very likely a made-up cause: the edit-controls read probably failed because of the same refused revision.
     - The card offers a retry that is probably futile. That conflicts with the "no futile reload" rule and the workspace rule against invented causes.
     - It is read-only, so it is not unsafe. It is confusing.
   - **Where it lands:** this is outside the restored code, so it does not block this conservation verdict. It should block owner acceptance of the SK-02/SK-06 error path.
   - **Suggested fix:** when the snapshot is refused, suppress or explain the edit-controls card instead of offering Retry.
2. **Medium (unconfirmed): the source refusal is not descriptive.** source-refused shows "Discovery failed. Check source access and refresh." It has no stable code, no Technical details, and no copy control.
   - For a disallowed local root, "refresh" is futile. The catalogue entry `local_source_not_allowed` says to choose a folder within an allowed root.
   - This matches SK-01 ("Source failures appear beneath the input"), so it may be existing behaviour rather than a conservation loss. I didn't compare it to an old source-node original.
   - It still falls short of the workspace's descriptive-error rule.
3. **Low: the Skill dropdown is clipped at 200% zoom.** In my-skills-discovered, the list runs past the top of the viewport, so `ace-practice-questions`, `claude-reviewer` and `code` can't be seen. Long entries are cut off at the right with no ellipsis.
4. **Low: the editor clips long lines at 1280 px.** In keyboard-and-background-refresh, lines 3, 7 and 19 are cut at the right edge. There is a horizontal scrollbar but no wrapping.
5. **Low: the history-diff column headers are cryptic.** The header row shows only single letters ("O"/"N", presumably old/new) above the line numbers. They are unlabelled and their meaning isn't shown.
6. **Low: the error card covers part of the modal.** In unsafe-current, the card sits over the modal's bottom-right area. It is dismissible and scoped to the modal, so this is acceptable.
7. **Info, inherited from pr-234:** the offline comparison's recovery text ("Select Current source…") doesn't mention the Reload files button shown below it.
8. **Info, docs:** SK-02's screenshot caption ("opened read-only", 2026-10-28) is now outdated, since the text is editable.

## Not covered by these images
- The history read failure path ("Reload history").
- An unknown failure reading the current files, with Reload.
- Redacting credential-shaped codes in the browser.
- The green "online" recovery card, and the low-height (≤300 px) popup layout.
- Escape key behaviour and keeping the global and modal popup stacks separate when both are present.
- Dark mode.
- The paused offline cross-flow case. It is documented as an inherited constraint and is not tested here.
- Real runner recovery and provider runs (there were zero model requests).
- The complete file-management and publishing stories.

## Scope
These screenshots and records show what happened in those runs. They don't prove the keyboard, mounting or abort timing claims, which rest on the story records. This visual approval is separate from the earlier CODE approvals. Owner validation, the complete SK-06 through SK-10 stories, provider and runner acceptance, and the semantic conservation review of all 23 old PRs are still open. This is not a merge approval.
