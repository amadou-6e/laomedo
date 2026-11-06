# PR254 Skills, Packet 2 review: frontend, integration patches, docs, examples and assets

**Scope:** `skills-followup-206`, base `37dc9aa9`, head `8938f9d4` (worktree `HEAD` → `refs/heads/refactor/206` = `8938f9d4`). I read all of `frontend.diff` (1–4026) and `presenter-fix.diff`. In `documentation.diff`, I read every doc, the example READMEs, `.gitattributes`, `build_flow.py`/`graph.py` and the `claude-agent` flow hunk; the rest is listed under "Not read" below. I also opened the five real-browser images and the sibling result JSONs, and grepped the isolated test and build logs.

## Packet 1 correction

My packet 1 isolation answer was wrong twice. I wrote that `skills/**` only uses `@/components/laomedoErrors/*` modules that develop already installs. That was false for `ErrorExplanation` (now fixed). I also never checked the catalogue keys those presenters look up. That second gap is still open at `8938f9d4` (D1).

## Isolation answer

**No.** Isolated `8938f9d4` still needs content that currently arrives with Shared255.

- **The `ErrorExplanation` fix holds.** I checked independently: the installer's error list now includes it (`tools/apply_langflow_skill_viewer.py:335-348`). Every other `@/components/laomedoErrors/*` module that `skills/**` imports (`CopyIcon`, `nodeErrors`, `ErrorPopup`, `NodeErrorNotice`, `node-error-catalog.json`) is in that same list.
- **The catalogue is still missing entries.** The exact missing prerequisite is the catalogue entries for:
  - `skill_inspection_unavailable`
  - `skill_history_unavailable`
  - `skill_comparison_unavailable`
  - `skill_revision_unavailable`
  - `skill_revision_unsafe`
  - `skill_revision_too_large`

The fix is to add these Skill-owned entries in PR254 itself. Merging Shared255 is not needed.

## Findings, most severe first

**PR254-F-D1 · defect · high · introduced** — `skills/interface/SkillInspectionError.tsx:5-15` (diff 2968-2978); `node-error-catalog.json` (diff 888-1014 adds none of these codes)
- **Trigger:** any file, history or comparison read failure on develop plus PR254 alone.
- **Mechanism:**
  - `describeNodeFailure(code)` finds no catalogue entry, so it uses the generic fallback (`nodeErrors.ts:15-19,107`).
  - The user sees "The node could not confirm completion… check the runner" instead of the Skill-specific text.
  - Refusals still hide Reload, because that check uses the code, but the explanation is wrong.
- **Evidence:** the isolated run at `frontend-jest.log:1-131,2018-2019` fails 3 suites and 41 tests (`SkillFilesModal`, `SkillHistory`, `SkillInspectionError`), and every failure received the fallback text.
- **Consequence:** the required descriptive read failures do not exist in isolated Skills.
- **The checkout hides this:** the review worktree's catalogue has these keys at lines 1587-1616 after the manual codes. The committed diff ends that file at `skill_manual_clipboard_unavailable` (diff 1009-1014), and the 8938 delta doesn't touch it. So the worktree contains catalogue content that is not in the own-diff, most likely uncommitted. The same applies to `test_errors.py:57-75` (`test_viewer_read_failures…`), which is absent from the backend own-diff. That content is unreviewed and not part of `8938f9d4`.

**PR254-F-Q1 · question (likely defect) · medium · introduced** — `skills/editor/SkillSourceEditor.tsx:1711,1719` (diff); README claim at diff 301-302
- **Trigger:** typing in a text file that starts with a UTF-8 BOM or has mixed line endings.
- **Mechanism:**
  - Monaco's `createModel` strips the BOM and normalises mixed EOLs.
  - `onDidChangeContent` then sends `model.getValue()` (which defaults to `preserveBOM=false`) through `update`.
  - `fileEdits` compares the text, so the saved file loses its BOM and its line endings are rewritten.
  - If the user reverts the visible edit, the file stays dirty with no visible difference.
- **Evidence:** this follows from Monaco's documented `getValue(eol?, preserveBOM?)` API. It was not reproduced. The only BOM test covers uploads (`SkillWorkingTree.test.ts:1771-1778`).
- **Requirement conflict:** the README promises "without BOM/newline normalisation".
- **Recheck:** a unit or browser test that edits a BOM file and a mixed-EOL file.

**PR254-F-Q2 · question · medium · introduced (frontend side of B-Q2)** — catalogue `skill_manual_stale` recovery (diff 944-948); `SkillEditing.tsx` publish (diff 1588); footer (diff 3818)
- **Trigger:** registry current moves outside the journal, then the user follows the recovery text: "inspect the refreshed diff and explicitly choose Publish again".
- **Mechanism:**
  - The refreshed `latest_revision` becomes `expected_latest`.
  - The footer only shows "N files to publish · Includes saved changes". It does not say that publishing will revert the external change.
- **Effect:** the user is guided straight into the B-Q2 overwrite.
- **Ask:** either add the ancestry check from B-Q2, or change this copy and label paths that would be reverted.

**PR254-F-D2 · defect (spec/docs) · low · introduced** — `docs/features/skills/user-stories.md` SK-08 (diff 882, 888)
- SK-08 says "Delete confirms" and puts "empty folders" outside the story.
- That contradicts the required behaviour (delete without confirmation, with undo/redo), SK09 and the code (`SkillFileManager.tsx` `remove`, diff 2318-2322).
- `manual-workspace.md` (diff 527-528) also lists empty folders as "unsupported", contradicting diff 439-444.

**PR254-F-S1 · suggestion · medium** — new presenter guard, `test_viewer.py` (presenter-fix.diff 34-68)
- The guard only checks module files in `skills/**/*.tsx`. That is why it missed D1.
- It skips `.ts` files, overlay-root adapters (`RenderAgentInputParameters` → `NodeErrorNotice`), and catalogue keys.
- **Suggestion:** also check that every literal code passed to `describeNodeFailure`, `describeInspectionFailure` or `ErrorPopup` in Skills exists in the committed catalogue.

**PR254-F-S2 · suggestion · low** — `ErrorExplanation.tsx` duplicates `ErrorPopup.tsx:12-18`
- These are two copies of the same explanation and copy format at the overlay root.
- I could not find the Shared255 copy within scope, so "exact Shared helper" is unverified.
- **Suggestion:** have `ErrorPopup` use the helper, or keep the helper Skill-owned and document that.

**PR254-F-S3 · suggestion (spec) · low-medium** — feature docs
- `manual-workspace.md`, `explorer.md`, `navigation-verification.md` and `workspace-viewer.md` are mostly revision-specific verification logs.
- They include stale reviewer-approval claims, e.g. "Claude approved code at `fbd3bd9`…" (diff 623-628).
- `import-history.md` says "Retry", but the UI now says "Reload history".
- `file-actions-narrow.png` shows the byte/hash row that has since been removed.
- This conflicts with "experiments only on exp, declarative docs".
- **Suggestion:** move the evidence narratives to exp and keep a declarative current guide.

**PR254-F-S4 · suggestion · low** — repo hygiene
- `.gitattributes:11` still lists the deleted `examples/skill-files-viewer/skill/**`.
- `examples/graph.py` moved to the examples root and was renamed to "maintained graph examples", but its only consumer is `examples/skills/build_flow.py:14`.

**PR254-F-Q3 · question (spec) · low**
- The explorer menu offers only Upload, Rename, Delete and Copy relative path (diff 2402-2408).
- There is no way to create a new file or folder; empty folders only appear after moving or deleting a last child.
- Is that enough for "empty folders" in a VS Code-like workspace?
- Also, Find's status says "pinned current" while the workspace shows the journal head rather than the graph pin (diff 3450 vs 1512-1515).

## What checks out

- **Corrections:**
  - Edit Request is hidden on the canvas, in the settings dialog and in the Inspection panel (installer patches, `SkillNodeControls.test.tsx`).
  - Revision is under the collapsed Advanced settings.
  - Only the exact failure string appears beneath a non-empty Source.
  - A blank Source shows "No source found".
- **Save/publish state:**
  - only one request can be in flight;
  - an unknown outcome keeps its exact request identity, and Check result resends the same body;
  - definitive codes clear the pending state;
  - a dirty buffer is never rebased;
  - a local import re-checks head and grant after its asynchronous read (diff 2335-2343).
- **Binary handling:**
  - `fileEdits` uses base64 for uploads and `source_path` for moved base files, and stays correct across repeated moves and undo.
  - Previews are recognised by magic bytes and bounded; SVG and PDF never reach `img`.
  - `validateEditSize` mirrors the ASCII relay's size calculation.
- **Paths:** new destinations reject traversal, drive paths and secret-like names; legacy paths are left alone.
- **Workspace lifetime:** `SkillViewerProvider` keeps the workspace open across canvas refreshes, and the `showCanvas` integration change matches `CanvasQueryState.test.ts`.

## Visual review (combined candidate 42a16c3; not isolated)

- **What the images show:**
  - read-only and editable compact headers, with "Graph pins";
  - Find, Files and Commits stacked in the explorer;
  - a selected-file diff against current;
  - a raster preview filling the pane after a real publication;
  - a descriptive outage card inside the viewport, with Retry edit controls.
- **V-Q1:** in `real-skill-history-settled.png`, the diff gutter header reads "O | N" but only one number column is visible. Is the old-index column rendering empty?
- **V-Q2:** in `real-skill-outage.png` (1024×720), the card covers the editor text and runs past the dialog's right edge. That is acceptable for a top-layer card, but please confirm.
- **Claims with no supporting image:** the five images do not show:
  - the node's "No source found" or failure-below-Source states (`real-skill-source.png` shows only the workspace);
  - the dirty footer or the discard modal;
  - inline rename, drag/drop or an empty folder;
  - the search tree or full-page mode.

  These rest on JSON claims (interactive) or dated docs images only.

## Verdicts

- **Implementation: REVISE.** D1 is proven by the isolated Jest failures. Q1 and Q2 are open.
- **Specification: REVISE.** D2 contradicts a stated requirement; S3 and Q3 are open.
- **Visual: INCOMPLETE.** All images come from the combined candidate, the isolated browser run is pending, and the states listed above have no images.
- **Not covered here:** user validation and merge.

## Evidence status

- **Isolated Python:** `skills-final-tests.log` — 127 OK, 3 skipped. That run may include the uncommitted worktree content.
- **Isolated Jest:** 41 failures across 3 suites.
- **Isolated build:** passes (`frontend-build.log:1940`).
- **Combined 1014/811 results:** not isolated acceptance.

## Not read

- `full.diff` on its own. I treated it as the union of the three diffs and only grepped it.
- `documentation.diff` 1166-3620: the deleted example bodies (`skill-files-viewer`, `skill-summary` and its executed and template flows). I checked only hunk headers and values.
- The other four `flow.json` hunks. I checked only that `code_hash` changes the same way as in `claude-agent`.
- The 26 dated docs PNGs.
- Applied but unchanged patches: `claude-models`, `claude-selection`, `catalog-recovery` and `agents.patch`, plus `upstream.patch` outside its two changed hunks.
- The pinned Langflow `package.json` (to confirm `uuid`, `base64-js`, `react-icons`, the Radix packages, `dompurify` and `react-markdown` are present) and the existence of `PageComponent/__tests__`.
- Where the deleted examples live: exp, and the archive revision `ea577c0`.
- The `real-skill-*.cjs` scripts.
- The isolated temp install, which is outside the allowed directory.
- The uncommitted worktree content.

## Recheck targets

1. Commit the inspection catalogue entries (D1). Rerun isolated Jest and confirm 0 failures, then rerun the isolated real browser.
2. Explain the worktree content that is not in the own-diff (catalogue, `test_errors.py`): commit it or drop it.
3. Add a BOM/mixed-EOL editing test (Q1).
4. Resolve the stale-recovery copy together with B-Q2 (Q2).
5. Fix the contradictions in SK-08 and `manual-workspace.md` (D2), and move the evidence logs to exp (S3).
6. Isolated screenshots of the Source states, the dirty footer, the discard modal and the file actions, plus V-Q1.