# Skill explorer

This is a historical verification record at the revision named below. The
[manual workspace guide](manual-workspace.md) owns the current editing, search
and review status; earlier read-only limits and pending-review notes below
refer to their recorded revision.

Files show a 16 px type logo before their name. Known extensions use the
appropriate bundled logo; unknown names/extensions have a generic file icon.
Recognized names such as Dockerfile also have a type logo. File rows reserve
the disclosure slot so root and nested entries align consistently.

Folders use the actual VS Code Codicon right/down chevrons. Click a folder or
focus it and press Enter/Space to expand or collapse it. Find, Files and Commits
headers use the same chevrons. Decorative icons do not change accessible names;
folder buttons retain aria-expanded. Long filenames truncate visually, with
their full relative path on hover. File selection, search, comparison and
read-only behavior are unchanged.

![Actual Skill explorer in light mode](assets/explorer-light.png)

![Actual Skill explorer in dark mode](assets/explorer-dark.png)

## Recorded checks

Recorded 2026-11-02, Windows/headless Edge, source `70571ca563eaae887c776dae0a40c642eaccc177`,
pinned Langflow `fec71dca901949c09ed4d63315804337cd2eb13d`. The existing saved
Skill is candidate `df5fad52`, with two genuine Markdown files, a references
folder and three history entries. No files, commits or model runs were added
to manufacture an icon demonstration. The task-owned Windows preview uses
a confirmed selector event loop after recovering an observed socket-accept
failure; this is viewer evidence, not new Agent-run acceptance.

| Actual browser story | Result |
| --- | --- |
| Type logos and alignment | Both real files have bundled 16 px Markdown SVGs. Root/nested indentation, decorative naming and absence of remote image elements pass. |
| Folder disclosure | Space collapses to chevron-right; Enter expands to chevron-down. The selected reference file remains selected and visible in source. |
| Navigation controls | Files header chevron, bulk Open/Collapse all and hide/restore retain the file and correct disclosure. |
| Viewports and themes | Normal/full-page and 900 × 650 layouts pass. Actual application Light/Dark controls were exercised, then the dedicated browser's theme settings restored. |
| Existing Find/history recovery | The complete workspace suite was rerun on this build. Cross-file search, current-source result navigation, full-page/restore, focus/Escape and real history outage/Retry passed. Retry recovered three entries in 172 ms. |
| Read-only boundary | No graph dispatches, Skill mutations or page errors in either run. Served JS/CSS assets match the exact build. The shipped icon attribution was retrieved and hash-verified. |

Fifty-one focused frontend unit controls pass, including type aliases,
case-insensitive suffixes, missing/unknown extensions and reserved-property
names. Those internal controls cover the other logo mappings; the live
demonstration uses the real Markdown files above. They do not establish new
Agent execution or GitHub-operation acceptance.

Icons use the existing react-icons dependency: Simple Icons and Microsoft
Codicons. No new package, CDN or remote icon request is introduced. The build
ships [icon attribution](../../../frontend/langflow-skill-viewer/skills/assets/skill-icons-NOTICE.txt)
as `/skill-icons-NOTICE.txt`.

The real keyboard check initially found that the canvas consumed Space on a
focused folder button. The viewer now isolates button Space events from canvas
panning while preserving native activation; the final real check repeats that
exact path. A browser asset-read failure and preview socket-accept failure were
recovered before these results, with no provider response substitution.

The [canonical SH10 editable proposal](https://github.com/amadou-6e/specs/pull/408)
and final code/visual review remain pending in the draft dependency. Earlier
review approval does not cover these changes. Requesting-owner validation is
also pending; no merge is authorized by this record.
