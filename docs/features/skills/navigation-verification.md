# Skill navigation and history verification

This is a historical verification record at the revision named below. The
[manual workspace guide](manual-workspace.md) owns the current editing, search
and review status; earlier read-only limits and pending-review notes below
refer to their recorded revision.

This capture predates workspace Find and full-page controls. See the
[latest viewer workflow and verification](workspace-viewer.md).

Recorded 2026-11-02 against implementation `ee2e66dc3537a218e1955fd7f490ebf87df6c1d9`:
Windows, headless Edge at 1600 × 1100, with an additional 1190 × 700 scroll check.
App and frontend use that source; exact wheel SHA256 is
`d42d1c81dbfaf13919f8196acb7a0113db9ce66b4002ff744d77d80f543f61ec`.
The frontend uses pinned Langflow `fec71dca901949c09ed4d63315804337cd2eb13d`;
102 served JavaScript/CSS responses matched the exact build bytes.

The [canonical navigation design](https://github.com/amadou-6e/specs/pull/408)
defines the state-aware action and retains individual chevrons.

| Real browser story | Observation |
| --- | --- |
| Open the selected Skill | Two actual files, including `references/pr-operation.md`, and three real commits. No Files/Commits action menus; one SKILL menu. |
| Collapse/open all | All sections and folders close/open. Mixed disclosure offers Open all. Selected file and commit remain unchanged. |
| Inspect each revision | The middle reference-file comparison has eight added rows; the imported-root comparison shows the added file; the current commit has no changes. Switching to SKILL.md retains the selected root and shows its added instruction line. Completed diff rows were checked, not just loading text. |
| Keyboard and pane controls | Keyboard activation, Escape/outside dismissal and focus return work. Hide/restore retains disclosure and selection; Reset navigation width returns to 280 px. |
| Preserve scroll | Commit history retains its 57 px scroll offset across closing/reopening its section in the smaller viewport. |
| Service failure/recovery | A real history-service outage shows History unavailable while files remain usable. Retry in the same dialog restores three entries in 157 ms. |
| Read-only browsing | No graph dispatch, Skill mutation or page error during navigation. No route interception or fake provider. |

![One SKILL menu with Collapse all and no section menus](assets/navigation-open.png)

![All sections closed, with Open all in the SKILL menu](assets/navigation-collapsed.png)

![Completed per-file comparison with three real history entries](assets/navigation-history.png)

## History provenance and limits

The current candidate is `sha256:df5fad5227d5175a546ce49f5adb0c1a9fee9cd4dc8cdbf82e9b4887aa28ba62`.
The existing imported root (`3032124f`, original import time unknown) parents
**Add PR operation contract** (`51b39b90`), then **Clarify PR update boundaries**
(`13f923bf`). The first operation changes two files; the second expands the
reference document. Both use actual authenticated ordinary Skill operations,
with trusted-backend-operator provenance. No model authorship is asserted.
The graph pins the returned candidate; canonical latest remains `4f0efb08`.
The narrow edit policy was removed and its service restarted afterward.

The earlier real Codex PR run used `4f0efb08`, not this new two-file candidate.
No Agent was dispatched or GitHub resource changed during this increment.
Twenty-four focused frontend controls passed; these support the real paths above.
Two initial browser harness assertions were corrected for hidden controls and
Hide navigation's divider focus. A transition screenshot was replaced only after
waiting for completed diff rows; product responses were not substituted.

Requesting-owner inspection and final user-story validation remain pending.
This record does not authorize merging or claim new Agent-run acceptance.
