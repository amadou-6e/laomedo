# Workspace Find and full-page viewing

Open **Skill files** from the selected Skill node. **Full page** fills the
browser viewport; **Restore window** returns to the normal viewer. Both keep
the selected file, commit, tabs, navigation width and search state.

In the SKILL sidebar, expand **Find** and enter text to search all text files in
the pinned current Skill revision. Matches are grouped by file with line numbers
and highlighted snippets. Click a result or focus it and press Enter to open
current source at its match. This exits a historical comparison explicitly;
historical-only files and binary contents are not searched. The viewer never
changes the selected revision or edits a file.

Click Find again to collapse it without losing the query. Ctrl/Cmd+F (also with
Shift) opens and focuses Find, restoring hidden navigation when necessary.
Escape inside Find collapses it and focuses its header; another Escape closes
the viewer. **Aa** enables case-sensitive literal matching. Empty/no-match
states are explicit, and searches with over 500 matching lines show the limit
and ask for a narrower query. Each line appears once, selecting its first match.
There is no separate Find in file button.

![Find across the real Skill's two files](assets/workspace-search.png)

![The same current source in full-page mode](assets/workspace-full-page.png)

## Recorded verification

Recorded 2026-11-02 against implementation `6c473d97324ee042ccc536a89ec95a3898d3ec72` on Windows,
headless Edge, pinned Langflow `fec71dca901949c09ed4d63315804337cd2eb13d`.
The actual saved graph uses the existing `pr-feedback-title` candidate
`df5fad52`, two files, a references folder and three genuine history entries.
Their [backend-operator provenance](navigation-verification.md#history-provenance-and-limits)
is unchanged; no new Agent authorship or run is claimed.

| Real browser story | Observed result |
| --- | --- |
| Search across the Skill | `proposal` finds four matching lines across SKILL.md and references/pr-operation.md. Case matching, empty/no-match recovery and repeated Find toggles work. |
| Open a result from history | Keyboard Enter opens current source and selects the match, exiting comparison. Repeated selection works. Typing cannot modify source. |
| Full page and restore | 1600 × 1100 full page at (0,0); normal/restored viewer is 1360 × 880 at (120,110). File, query, commit and navigation width survive. Settled restore took 520 ms in this run. |
| Smaller viewport | After the resize transition settles, full page is 900 × 650 at (0,0), restored viewer is 765 × 520 at (67.5,65). Controls stay within the viewport. |
| Keyboard/navigation | Header and source shortcuts, Escape/focus return, dialog focus trapping, bulk collapse/open and shortcut restoration of hidden navigation pass. |
| Real history outage/recovery | With the task's actual history service stopped, History unavailable appears while local search works. After restoring the same service/journal, Retry recovers all three entries in 294 ms without clearing the query. |
| Read-only boundary | Zero graph dispatches, Skill mutations or page errors; 102 served JS/CSS responses match the exact build hashes. No route interception, fake provider or new model turn. |

The original button's failure was reproduced before deployment. The reused
browser initially retained the old application; a normal reload loaded the
verified new assets. A resize assertion was corrected to wait for the actual
transition, and both small-viewport captures were repeated after settling.
Product responses were not replaced. Twenty-seven focused frontend unit tests
pass as supporting controls, including literal escaping, Unicode positions,
binary exclusion, inert markup and result truncation. The updated fixture-based
browser regression was syntax-checked, not run as live acceptance.

The [canonical editable design and contract](https://github.com/amadou-6e/specs/pull/408)
contain SH08/SH09 in a draft specification dependency. Final independent review
of these changes and requesting-owner user-story validation remain pending.
This record does not authorize merging. Browser profile/session management and
interactive streaming are not capabilities added by this read-only viewer.
