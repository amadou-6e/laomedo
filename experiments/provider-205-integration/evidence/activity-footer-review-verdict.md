# Activity footer review (b9765179 → fd34cb7e)

**Bottom line:** the footer code and layout are fine and I found no defects. One point needs your decision: the footer says "MIT License", but the repository has no license file and no license metadata, so nothing in the repo backs that claim yet.

## Code and docs

`activity-footer.diff` was read in full.

- **Placement:** the `<footer>` sits after the `{detail&&<article>}` block, inside the main scroll `div` (`GraphAgents.tsx:158-160`). It renders whether or not a run is selected, which matches your before-selection check.
- **Styling:** `mt-12 border-t pt-6 pb-16 text-center text-xs text-muted-foreground`. It has no state, no data dependency and no interaction.
- **Year:** `new Date().getFullYear()` uses the viewer's local clock, which is fine for a notice.
- **Ordering:** the conversation still comes after `RuntimeRecords`, consistent with your revert. That confirms the reorder is gone; I did not separately check that the files at b9765179 equal bca47f11.
- **README:** documents the muted footer and its spacing accurately.
- **Nothing else changed:** no Python, no test edits, and no license or package metadata.

## Image inspected

**`activity-footer-redacted.png`** (773×714, scrolled to the end):
- The page shows OpenTelemetry ("No OpenTelemetry records captured"), then Conversation with "2 of 2", the masked "You" bubble and the masked Codex reply, then a full-width divider, then "© 2026 Laomedo contributors. MIT License." centred and muted.
- There is clear space between the last message and the divider, with bottom padding after the notice.
- Nothing overlaps or is clipped, and there is no horizontal overflow.
- The grey footer text is legible on white. The colour comes from the existing `muted-foreground` theme token; I did not measure contrast.

**Limits:**
- The masks hide the message text, so I can't judge how the last message wraps against the footer.
- Dark theme is not shown.
- This is the standalone render, not the owner's screenshot. I relied on your report for the integrated browser and for the 48px/64px computed values.

## Findings

**L-01 (material question for the owner, not a code defect): the license claim has no backing in the repository.**
- I found no `LICENSE` file at the repository root (`C:/CodeWorkspace/laomedo/LICENSE` does not exist).
- `pyproject.toml` declares no `license` field.
- The footer is what the owner asked for. But until a `LICENSE` file (with the full MIT text and copyright holder) and the matching package metadata are added, the visible notice asserts a license that isn't recorded anywhere in the repository.
- Recommendation: add the license file and metadata in a separate, owner-approved change, or have the owner confirm that a notice in the UI alone is intended. I am not proposing or approving a licensing change here.

**Optional:** the "Laomedo contributors" holder wording is fine and names no individual. Keep it consistent with whatever `LICENSE` text is later added.

## Verdicts

- **Code and docs:** APPROVE.
- **Visual:** APPROVE, limited to spacing, placement, separation and legibility in the masked standalone render. It does not cover message-text rendering, dark theme, or the owner's exact view.
- **Licensing:** not determined by this review; L-01 is for the owner.
- **Not authorized:** merge or issue closure.